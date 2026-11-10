import os
import tempfile
import shutil
import json
import html
from flask import Flask, render_template, request, send_file, jsonify, after_this_request
import yt_dlp
import threading
import time
import requests
from bs4 import BeautifulSoup
import re
import atexit

app = Flask(__name__)

# Configure upload folder for temporary files
TEMP_FOLDER = tempfile.mkdtemp()
app.config['TEMP_FOLDER'] = TEMP_FOLDER
atexit.register(shutil.rmtree, TEMP_FOLDER, ignore_errors=True)

def cleanup_file(filepath):
    """Delete file after a delay"""
    def delete_after_delay():
        time.sleep(30)  # Wait 30 seconds before cleanup
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except:
            pass

    thread = threading.Thread(target=delete_after_delay)
    thread.daemon = True
    thread.start()

_SEARCH_STOPWORDS = {
    "a", "an", "and", "by", "feat", "ft", "for", "free", "instrumental", "official",
    "of", "on", "prod", "producer", "remix", "type", "video", "audio", "music",
    "beat", "beats", "x", "w", "with", "the", "to",
}

def _tokenize_search_text(text):
    if not text:
        return set()
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t and t not in _SEARCH_STOPWORDS and len(t) > 1}

def _infer_beat_title_from_slug(slug):
    if not slug:
        return None
    text = slug.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()

    # Common Beatstars SEO slugs: "... type beat <TITLE>"
    match = re.search(r"\btype\s*beat\b\s+(.*)$", text, flags=re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        prefix = text[:match.start()].strip()

        # Pull meaningful "genre" context from the prefix to avoid overly-generic titles like "Class".
        prefix_tokens = [
            t for t in re.findall(r"[a-z0-9]+", prefix.lower())
            if t and t not in _SEARCH_STOPWORDS and t not in {"type", "beat"}
        ]
        prefix_phrase = " ".join(prefix_tokens[:6]).strip()

        if candidate:
            if prefix_phrase:
                return f"{prefix_phrase} {candidate}".title()
            return candidate.title()

    # Otherwise take the last 1–3 words (often the actual beat name).
    words = [w for w in text.split(" ") if w]
    if not words:
        return None
    tail = " ".join(words[-3:]).strip()
    return tail.title() if tail else None

def _extract_beat_info_from_nuxt(data):
    """Recursively search Nuxt payloads for beat metadata."""
    if isinstance(data, dict):
        beat_data = data.get('beat')
        if isinstance(beat_data, dict):
            title = beat_data.get('title') or beat_data.get('name')
            producer_name = None
            producer_data = (
                beat_data.get('producer') or
                beat_data.get('user') or
                beat_data.get('creator') or
                beat_data.get('owner')
            )
            if isinstance(producer_data, dict):
                for key in ('display_name', 'name', 'username', 'title'):
                    if producer_data.get(key):
                        producer_name = producer_data.get(key)
                        break
            elif isinstance(producer_data, str):
                producer_name = producer_data

            if title:
                return title, producer_name or "Beatstars Producer"

        # Some payloads might expose the beat directly
        possible_title = data.get('title') or data.get('name')
        if possible_title:
            producer_name = None
            for key in ('producer_name', 'producerName', 'producer', 'creator', 'user'):
                value = data.get(key)
                if isinstance(value, dict):
                    for attr in ('display_name', 'name', 'username', 'title'):
                        if value.get(attr):
                            producer_name = value.get(attr)
                            break
                    if producer_name:
                        break
                elif isinstance(value, str) and value.strip():
                    producer_name = value.strip()
                    break

            if producer_name:
                return possible_title, producer_name

        for value in data.values():
            result = _extract_beat_info_from_nuxt(value)
            if result:
                return result

    elif isinstance(data, list):
        for item in data:
            result = _extract_beat_info_from_nuxt(item)
            if result:
                return result

    return None


def _load_nuxt_payload(page_content):
    """Extract window.__NUXT__ JSON structures from Beatstars player pages."""
    if not page_content:
        return None

    # Beatstars player uses Nuxt and exposes data via window.__NUXT__.
    # Regex alone is brittle here because the JSON can contain nested braces; scan for balanced braces instead.
    marker_match = re.search(r'window\.__NUXT__\s*=\s*', page_content)
    if not marker_match:
        return None

    start = marker_match.end()
    tail = html.unescape(page_content[start:])

    # Skip whitespace
    i = 0
    while i < len(tail) and tail[i].isspace():
        i += 1
    if i >= len(tail) or tail[i] not in "{[":
        return None

    opening = tail[i]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    end_index = None

    for j in range(i, len(tail)):
        ch = tail[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                end_index = j + 1
                break

    if end_index is None:
        return None

    json_str = tail[i:end_index]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def fetch_beatstars_embed_metadata(beat_id):
    """Fetch beat metadata from Beatstars player embed pages."""
    if not beat_id:
        return None

    embed_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.beatstars.com/'
    }

    embed_urls = [
        f"https://player.beatstars.com/beat/{beat_id}",
        f"https://player.beatstars.com/?beatId={beat_id}",
        f"https://player.beatstars.com/?trackId={beat_id}"
    ]

    for embed_url in embed_urls:
        try:
            response = requests.get(embed_url, headers=embed_headers, timeout=15)
            if response.status_code == 200:
                nuxt_payload = _load_nuxt_payload(response.text)
                if nuxt_payload:
                    result = _extract_beat_info_from_nuxt(nuxt_payload)
                    if result:
                        return result
        except requests.RequestException as err:
            print(f"Beatstars embed metadata request failed for {embed_url}: {err}")
            continue

    return None


def extract_beatstars_info(beatstars_url):
    """Extract beat information from Beatstars URL"""
    try:
        # Extract beat ID from URL
        url_match = re.search(r'/beat/(?:([^/]+)-)?(\d+)', beatstars_url)
        if not url_match:
            return None, None

        beat_slug = url_match.group(1)
        beat_id = url_match.group(2)
        print(f"Extracted Beatstars beat ID: {beat_id}, slug: {beat_slug}")

        slug_fallback_title = None
        if beat_slug:
            # Prefer a smaller "actual title" guess if the slug is SEO-heavy.
            slug_fallback_title = _infer_beat_title_from_slug(beat_slug) or beat_slug.replace('-', ' ').title()

        # Try to get beat information from the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.beatstars.com/'
        }

        response = requests.get(beatstars_url, headers=headers, timeout=15)
        if response.status_code == 200:
            raw_content = response.text

            # Beatstars often exposes full metadata via window.__NUXT__ on the main page
            nuxt_payload = _load_nuxt_payload(raw_content)
            if nuxt_payload:
                nuxt_result = _extract_beat_info_from_nuxt(nuxt_payload)
                if nuxt_result:
                    return nuxt_result

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for beat title in various places
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                title_text = title_tag.string.strip()
                print(f"Found title from Beatstars: {title_text}")

                # Check if this is a generic Beatstars page (not a specific beat)
                if "Buy Beats Online" in title_text or "Download Beats" in title_text:
                    print("This appears to be a generic Beatstars page; falling back to embed/slug parsing")
                    # Don't early-return here; the player embed often has the real title/producer.
                    title_text = None

                # Clean up title (remove "Beatstars -" prefix, etc.)
                if title_text:
                    title_text = re.sub(r'^Beatstars\s*-\s*', '', title_text)
                    title_text = re.sub(r'\s*\|\s*Beatstars.*$', '', title_text)

                # Look for producer/artist name in more places
                producer_name = None

                # Try to find meta tags
                meta_tags = soup.find_all('meta')
                for tag in meta_tags:
                    if tag.get('property') == 'og:title':
                        og_title = tag.get('content', '')
                        print(f"Found OG title: {og_title}")
                        if '|' in og_title:
                            parts = og_title.split('|', 1)
                            beat_title = parts[0].strip()
                            producer_name = parts[1].strip()
                            return beat_title, producer_name or "Unknown Producer"
                        elif ' - ' in og_title:
                            parts = og_title.split(' - ', 1)
                            beat_title = parts[0].strip()
                            producer_name = parts[1].strip()
                            return beat_title, producer_name or "Unknown Producer"
                        elif '-' in og_title and len(og_title.split('-')) == 2:
                            parts = og_title.split('-', 1)
                            beat_title = parts[0].strip()
                            producer_name = parts[1].strip()
                            return beat_title, producer_name or "Unknown Producer"

                # Look for structured data (JSON-LD)
                json_scripts = soup.find_all('script', type='application/ld+json')
                for script in json_scripts:
                    if script.string:
                        try:
                            import json
                            data = json.loads(script.string)
                            if isinstance(data, dict):
                                # Look for music recording data
                                if data.get('@type') == 'MusicRecording':
                                    beat_title = data.get('name', '')
                                    producer_name = None
                                    if 'byArtist' in data:
                                        producer_name = data['byArtist'].get('name', '')
                                    if beat_title:
                                        return beat_title, producer_name or "Beatstars Producer"
                        except:
                            continue

                # Try to decode inline JSON blobs for beat/producer data
                script_tags = soup.find_all('script')
                for script in script_tags:
                    script_content = script.string or script.text
                    if not script_content:
                        continue

                    # Look for window.__NUXT__ assignment inside the script itself
                    nuxt_match = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\})\s*;', script_content, re.DOTALL)
                    candidate_json = None
                    if nuxt_match:
                        candidate_json = nuxt_match.group(1)
                    else:
                        trimmed = script_content.strip()
                        if trimmed.startswith('{') or trimmed.startswith('['):
                            candidate_json = trimmed

                    if candidate_json:
                        try:
                            data = json.loads(candidate_json)
                            result = _extract_beat_info_from_nuxt(data)
                            if result:
                                return result
                        except Exception:
                            # Skip scripts that are not pure JSON
                            pass

                # Regex fallback when JSON parsing fails but page contains producer hints
                producer_match = re.search(r'"producer"\s*:\s*\{[^}]*?"display_name"\s*:\s*"([^"]+)"', raw_content)
                title_match = re.search(r'"title"\s*:\s*"([^"]+)"', raw_content)
                if title_match:
                    beat_title = html.unescape(title_match.group(1))
                    if producer_match:
                        return beat_title, html.unescape(producer_match.group(1))
                    return beat_title, producer_name or "Beatstars Producer"

                # Look for specific Beatstars page elements
                # Search for elements containing artist/producer information
                artist_selectors = [
                    'span.artist-name',
                    'div.producer-name',
                    'h2.producer',
                    'a[href*="/user/"]',
                    '.beat-artist',
                    '.producer-link'
                ]

                for selector in artist_selectors:
                    elements = soup.select(selector)
                    for element in elements:
                        text = element.get_text().strip()
                        if text and len(text) > 2 and not text.isdigit():
                            print(f"Found artist element: {text}")
                            producer_name = text
                            break
                    if producer_name:
                        break

                # Look for beat title in specific elements
                title_selectors = [
                    'h1.beat-title',
                    'div.beat-name',
                    '.track-title',
                    '.beat-header h1'
                ]

                beat_title = None
                for selector in title_selectors:
                    elements = soup.select(selector)
                    for element in elements:
                        text = element.get_text().strip()
                        if text and len(text) > 2:
                            print(f"Found beat title element: {text}")
                            beat_title = text
                            break
                    if beat_title:
                        break

                # If we found both title and producer, return them
                if beat_title and producer_name:
                    return beat_title, producer_name

                # If we found just the producer, use the cleaned title
                if producer_name and title_text and not ("Buy Beats" in title_text):
                    return title_text, producer_name

                # Look for h1 tags that might contain the beat title
                h1_tags = soup.find_all('h1')
                for h1 in h1_tags:
                    if h1.string and len(h1.string.strip()) > 3:
                        beat_title = h1.string.strip()
                        print(f"Found H1 title: {beat_title}")
                        return beat_title, producer_name or "Beatstars Producer"

                # If we found a title but no producer, return just the title
                if title_text and not ("Buy Beats" in title_text):
                    return title_text, "Beatstars Producer"

        # Fallback to Beatstars player embed (works for slugless URLs)
        embed_metadata = fetch_beatstars_embed_metadata(beat_id)
        if embed_metadata:
            return embed_metadata

        # Fallback: extract from URL slug
        if slug_fallback_title:
            return slug_fallback_title, "Beatstars Producer"

        return f"Beatstars Beat {beat_id}", "Beatstars Producer"

    except Exception as e:
        print(f"Error extracting Beatstars info: {e}")
        return None, None

def extract_spotify_info(spotify_url):
    """Extract track information from Spotify URL"""
    try:
        # First, try to extract from URL pattern
        url_match = re.search(r'/track/([a-zA-Z0-9]+)', spotify_url)
        if url_match:
            track_id = url_match.group(1)
            print(f"Extracted Spotify track ID: {track_id}")

            # Try multiple approaches to get track info

            # Approach 1: Use Spotify's embed endpoint (often has more accessible data)
            embed_url = f"https://open.spotify.com/embed/track/{track_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://open.spotify.com/'
            }

            response = requests.get(embed_url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')

                # Look for track title in various places
                title_tag = soup.find('title')
                if title_tag and title_tag.string:
                    title_text = title_tag.string.strip()
                    print(f"Found title from embed: {title_text}")

                    # Try to parse "Track Name - Artist Name" format
                    if ' - ' in title_text:
                        parts = title_text.split(' - ', 1)
                        track_name = parts[0].strip()
                        artist_name = parts[1].strip()
                        if track_name and artist_name:
                            return track_name, artist_name

                # Look for JSON data in scripts
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and ('Spotify.Entity' in script.string or 'entity' in script.string):
                        print(f"Found script with entity data, length: {len(script.string)}")
                        # Try to extract from JSON data
                        try:
                            import json

                            # Look for JSON objects in the script
                            json_start = script.string.find('{')
                            json_end = script.string.rfind('}') + 1

                            if json_start != -1 and json_end > json_start:
                                json_str = script.string[json_start:json_end]
                                data = json.loads(json_str)

                                # Navigate through the nested structure
                                if 'props' in data and 'pageProps' in data['props']:
                                    state = data['props']['pageProps'].get('state', {})
                                    entity_data = state.get('data', {}).get('entity', {})

                                    if entity_data.get('type') == 'track':
                                        track_name = entity_data.get('name')
                                        artists = entity_data.get('artists', [])
                                        if artists and len(artists) > 0:
                                            artist_name = artists[0].get('name')

                                            if track_name and artist_name:
                                                print(f"Successfully extracted: '{track_name}' by '{artist_name}'")
                                                return track_name, artist_name

                        except json.JSONDecodeError:
                            # Try regex approach as fallback
                            name_match = re.search(r'"name"\s*:\s*"([^"]+)"', script.string)
                            if name_match:
                                track_name = name_match.group(1)
                                print(f"Found track name via regex: {track_name}")

                                # Look for artist name in artists array
                                artist_match = re.search(r'"artists"\s*:\s*\[\s*\{[^}]*"name"\s*:\s*"([^"]+)"', script.string)
                                if artist_match:
                                    artist_name = artist_match.group(1)
                                    print(f"Found artist name via regex: {artist_name}")
                                    return track_name, artist_name
                        except Exception as e:
                            print(f"Error parsing script: {e}")
                            continue

            # Approach 2: Try the main Spotify page with better headers
            headers_main = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5,en;q=0.3',
                'Referer': 'https://www.google.com/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }

            response = requests.get(spotify_url, headers=headers_main, timeout=15)
            if response.status_code == 200 and len(response.content) > 1000:  # Make sure we got actual content
                soup = BeautifulSoup(response.content, 'html.parser')

                # Look for title tag
                title_tag = soup.find('title')
                if title_tag and title_tag.string:
                    title_text = title_tag.string.strip()
                    print(f"Found title from main page: {title_text}")

                    # Parse different title formats
                    if '|' in title_text:
                        parts = title_text.split('|', 1)
                        if len(parts) >= 2:
                            track_name = parts[0].strip()
                            artist_name = parts[1].strip()
                            return track_name, artist_name
                    elif ' - ' in title_text:
                        parts = title_text.split(' - ', 1)
                        track_name = parts[0].strip()
                        artist_name = parts[1].strip()
                        return track_name, artist_name

                # Look for meta tags
                meta_tags = soup.find_all('meta')
                for tag in meta_tags:
                    if tag.get('property') == 'og:title':
                        og_title = tag.get('content', '')
                        print(f"Found OG title: {og_title}")
                        if '|' in og_title:
                            parts = og_title.split('|', 1)
                            if len(parts) >= 2:
                                return parts[0].strip(), parts[1].strip()

        # If all approaches fail, return None
        print("Could not extract track information from Spotify URL")
        return None, None

    except Exception as e:
        print(f"Error extracting Spotify info: {e}")
        return None, None

def search_youtube_track(track_name, artist_name):
    """Search for track on YouTube and return the best match URL"""
    if not track_name:
        return None

    try:
        # Try different search queries for better results
        search_queries = [
            f"{artist_name} {track_name} official audio" if artist_name else f"{track_name} official audio",
            f"{artist_name} {track_name} official music video" if artist_name else f"{track_name} music video",
            f"{artist_name} {track_name}" if artist_name else f"{track_name}"
        ]

        for search_query in search_queries:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch3',  # Get top 3 results
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    search_results = ydl.extract_info(f"ytsearch3:{search_query}", download=False)

                    if search_results and 'entries' in search_results and search_results['entries']:
                        # Look for the best match (prefer official audio/official video)
                        for entry in search_results['entries']:
                            title = entry.get('title', '').lower()
                            if any(keyword in title for keyword in ['official audio', 'official music video', 'official video']):
                                video_id = entry.get('id') or entry.get('url', '').split('/')[-1].split('?')[0]
                                return f"https://www.youtube.com/watch?v={video_id}"

                        # If no official version found, return the first result
                        first_result = search_results['entries'][0]
                        video_id = first_result.get('id') or first_result.get('url', '').split('/')[-1].split('?')[0]
                        return f"https://www.youtube.com/watch?v={video_id}"
                except:
                    continue  # Try next search query

    except Exception as e:
        print(f"Error searching YouTube: {e}")

    return None

def search_youtube_beat(beat_name, producer_name):
    """Search for beat on YouTube and return the best match URL"""
    if not beat_name:
        return None

    try:
        beat_tokens = _tokenize_search_text(beat_name)
        producer_tokens = _tokenize_search_text(producer_name) if producer_name else set()
        require_producer = bool(producer_tokens) and producer_name not in ["Beatstars Producer", "Unknown Producer"]
        generic_beat_query = len(beat_tokens) <= 1

        # Beat-specific search queries - prioritize artist name when available
        search_queries = []

        # If we have a producer name that's not generic, prioritize it
        if require_producer:
            search_queries.extend([
                f"\"{beat_name}\" {producer_name}" if generic_beat_query else None,
                f"{beat_name} {producer_name}",  # Exact match like "Plus Jamais Layton"
                f"{beat_name} by {producer_name}",
                f"{producer_name} {beat_name} beat",
                f"{producer_name} {beat_name}"
            ])

        search_queries = [q for q in search_queries if q]

        # General beat searches
        search_queries.extend([
            f"{beat_name} beat instrumental",
            f"{beat_name} type beat",
            f"{beat_name} prod",
            f"{beat_name} beat free",
            f"{beat_name} instrumental beat"
        ])

        best_url = None
        best_score = 0.0

        for search_query in search_queries:
            print(f"Trying beat search: {search_query}")
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch8',  # Get top 8 results for beats
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    search_results = ydl.extract_info(f"ytsearch8:{search_query}", download=False)

                    if search_results and 'entries' in search_results and search_results['entries']:
                        print(f"Found {len(search_results['entries'])} results for '{search_query}'")

                        # Look for beat/instrumental content (avoid tutorials and vocal tracks)
                        for entry in search_results['entries']:
                            title = entry.get('title', '').lower()
                            description = entry.get('description', '').lower() if entry.get('description') else ''

                            print(f"  Checking: {entry.get('title', '')}")

                            # Skip tutorial videos, vocal tracks, and non-beat content
                            skip_keywords = ['tutorial', 'how to', 'export', 'fl studio', 'logic pro', 'ableton', 'vocal', 'lyrics', 'singing', 'cover', 'remix']
                            if any(keyword in title or keyword in description for keyword in skip_keywords):
                                print(f"    Skipping (contains skip keywords)")
                                continue

                            uploader = (entry.get('uploader') or entry.get('channel') or entry.get('uploader_id') or '').lower()
                            combined_text = f"{title} {description} {uploader}"
                            combined_tokens = _tokenize_search_text(combined_text)

                            # Beat match: token overlap (handles different word orders / extra SEO words)
                            beat_overlap = 0.0
                            if beat_tokens:
                                beat_overlap = len(beat_tokens & combined_tokens) / max(1, len(beat_tokens))

                            producer_overlap = 0.0
                            if producer_tokens:
                                producer_overlap = len(producer_tokens & combined_tokens) / max(1, len(producer_tokens))

                            # Prefer beat-ish results even when overlap is decent.
                            prefer_keywords = ['beat', 'instrumental', 'type beat', 'prod', 'producer', 'free beat', 'demo', 'boombap', 'trap beat']
                            prefer_bonus = 0.10 if any(k in combined_text for k in prefer_keywords) else 0.0

                            score = beat_overlap + (0.75 * producer_overlap) + prefer_bonus
                            if require_producer and producer_overlap == 0.0:
                                # If the beat title is generic (e.g., "Class"), don't accept results that don't mention the producer.
                                if generic_beat_query:
                                    continue
                                score -= 0.35  # penalize results that don't mention the producer at all

                            # Keep best candidate across all queries.
                            if score > best_score:
                                video_id = entry.get('id') or entry.get('url', '').split('/')[-1].split('?')[0]
                                if video_id:
                                    best_score = score
                                    best_url = f"https://www.youtube.com/watch?v={video_id}"
                                    print(f"    New best score {best_score:.2f}: {entry.get('title', '')}")

                except Exception as e:
                    print(f"Error with search query '{search_query}': {e}")
                    continue

    except Exception as e:
        print(f"Error searching YouTube for beat: {e}")

    # Only accept if match looks plausible (avoid returning unrelated beats).
    if best_url and best_score >= (0.55 if require_producer else 0.40):
        return best_url

    return None

def search_youtube_beat_simple(search_query, search_type):
    """Simple YouTube search for beats - returns first non-tutorial result"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch5',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(f"ytsearch5:{search_query}", download=False)

            if search_results and 'entries' in search_results and search_results['entries']:
                # Return the first non-tutorial result
                for entry in search_results['entries']:
                    title = entry.get('title', '').lower()
                    description = entry.get('description', '').lower() if entry.get('description') else ''

                    # Skip tutorials
                    if not any(keyword in title or keyword in description for keyword in ['tutorial', 'how to', 'export', 'fl studio']):
                        video_id = entry.get('id') or entry.get('url', '').split('/')[-1].split('?')[0]
                        return f"https://www.youtube.com/watch?v={video_id}"

    except Exception as e:
        print(f"Error in simple beat search: {e}")

    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_video():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'Please provide a URL'}), 400

        # Validate URL (YouTube, YouTube Music, SoundCloud, Spotify, or Beatstars)
        if not (('youtube.com' in url or 'youtu.be' in url or 'music.youtube.com' in url) or ('soundcloud.com' in url) or ('spotify.com' in url or 'open.spotify.com' in url) or ('beatstars.com' in url)):
            return jsonify({'error': 'Please provide a valid YouTube, YouTube Music, SoundCloud, Spotify, or Beatstars URL'}), 400
        
        # Handle Spotify and Beatstars URLs by finding the track/beat on YouTube
        original_url = url
        is_spotify = 'spotify.com' in url or 'open.spotify.com' in url
        is_beatstars = 'beatstars.com' in url
        artist_override = (data.get('artist') or data.get('artistName') or data.get('producer') or '').strip() or None

        if is_spotify:
            # Extract track info from Spotify
            track_name, artist_name = extract_spotify_info(url)

            if not track_name:
                return jsonify({'error': 'Could not extract track information from Spotify URL. Please try a different Spotify link or use the direct YouTube/SoundCloud link instead.'}), 400

            # Search for the track on YouTube
            youtube_url = search_youtube_track(track_name, artist_name)

            if not youtube_url:
                return jsonify({'error': f'Could not find "{track_name}" by {artist_name or "Unknown Artist"} on YouTube. Please try searching manually or use a different link.'}), 400

            # Use the YouTube URL instead
            url = youtube_url
            print(f"Spotify track found: '{track_name}' by {artist_name or 'Unknown Artist'} -> {youtube_url}")

        elif is_beatstars:
            # Extract beat info from Beatstars
            beat_name, producer_name = extract_beatstars_info(url)

            # Allow user-provided artist/producer to override detection for accuracy
            if artist_override:
                producer_name = artist_override

            if not beat_name:
                return jsonify({'error': 'Could not extract beat information from Beatstars URL. Please try a different Beatstars link or use the direct YouTube/SoundCloud link instead.'}), 400

            # For Beatstars beats, try some common producer names if we don't have one
            if producer_name in ["Beatstars Producer", "Unknown Producer"]:
                # Try searching with common variations of the beat name
                # This is a workaround since Beatstars pages often don't show producer info
                common_searches = [
                    f"\"{beat_name}\"",
                    f"{beat_name} type beat",
                    f"{beat_name} beat"
                ]

                for search_term in common_searches:
                    print(f"Trying direct search: {search_term}")
                    temp_youtube_url = search_youtube_beat_simple(search_term, "direct")
                    if temp_youtube_url:
                        url = temp_youtube_url
                        print(f"Found beat with direct search: {search_term} -> {temp_youtube_url}")
                        break
                else:
                    # If direct searches fail, use the normal beat search
                    youtube_url = search_youtube_beat(beat_name, producer_name)
                    if not youtube_url:
                        return jsonify({'error': f'Could not find "{beat_name}" beat on YouTube. Please try searching manually or use a different link.'}), 400
                    url = youtube_url
            else:
                # We have a producer name, use normal search
                youtube_url = search_youtube_beat(beat_name, producer_name)
                if not youtube_url:
                    return jsonify({'error': f'Could not find "{beat_name}" beat on YouTube. Please try searching manually or use a different link.'}), 400
                url = youtube_url

            print(f"Beatstars beat found: '{beat_name}' by {producer_name or 'Unknown Producer'} -> {url}")

        # Create unique filename
        timestamp = str(int(time.time()))
        output_filename = f"audio_{timestamp}.%(ext)s"
        output_path = os.path.join(app.config['TEMP_FOLDER'], output_filename)
        mp3_filename = f"audio_{timestamp}.mp3"
        mp3_path = os.path.join(app.config['TEMP_FOLDER'], mp3_filename)

        # Configure yt-dlp options based on platform
        is_soundcloud = 'soundcloud.com' in url
        is_youtube_music = 'music.youtube.com' in url

        base_opts = {
            # Use a broadly compatible audio selector; we also try additional fallbacks below.
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'extractor_retries': 3,
            'cookiefile': None,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'retries': 3,
            'fragment_retries': 3,
            'noplaylist': True,
            'geo_bypass': True,
        }

        # Let the bundled yt-dlp choose current YouTube clients.
        if is_soundcloud:
            # SoundCloud-specific settings to get full tracks
            platform_opts = {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://soundcloud.com/',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                },
                # Additional SoundCloud options
                'extractor_args': {
                    'soundcloud': {
                        'client_id': None,  # Let yt-dlp find the best client_id
                    }
                }
            }

            # Try to get more info about the track to detect Go+ content
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as temp_ydl:
                    temp_info = temp_ydl.extract_info(url, download=False)
                    if temp_info and 'duration' in temp_info:
                        track_duration = temp_info.get('duration', 0)
                        # If duration is exactly 30 seconds, it's likely a Go+ preview
                        if track_duration == 30:
                            print(f"Warning: Track appears to be SoundCloud Go+ content (30s preview detected)")
            except:
                pass
        else:
            platform_opts = {}

        platform_attempts = [platform_opts]
        ydl_opts = {**base_opts, **platform_opts}

        # Check for SoundCloud Go+ content
        is_go_plus = False
        if is_soundcloud and not is_youtube_music:
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as temp_ydl:
                    temp_info = temp_ydl.extract_info(url, download=False)
                    if temp_info and 'duration' in temp_info:
                        track_duration = temp_info.get('duration', 0)
                        # If duration is exactly 30 seconds, it's likely a Go+ preview
                        if track_duration == 30:
                            is_go_plus = True
            except:
                pass

        # Download and convert with fallback options
        video_title = 'Unknown'
        download_successful = False

        # Try different format combinations
        format_options = [
            'bestaudio/best',
            'bestaudio[acodec!=none]/best[acodec!=none]',
            'worstaudio/worst',
            'best'  # Ultimate fallback
        ]

        for format_option in format_options:
            for attempt_opts in platform_attempts:
                try:
                    ydl_opts = {**base_opts, **attempt_opts}
                    ydl_opts['format'] = format_option
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Get video info first
                        info = ydl.extract_info(url, download=False)
                        video_title = info.get('title', 'Unknown')

                        # Download and convert
                        ydl.download([url])

                        # Check if output file was created
                        if os.path.exists(mp3_path):
                            # Check if it's a 30-second Go+ preview
                            try:
                                import mutagen
                                from mutagen.mp3 import MP3
                                audio = MP3(mp3_path)
                                duration = audio.info.length
                                if duration <= 35 and is_go_plus:  # Allow some tolerance
                                    return jsonify({'error': 'This appears to be a SoundCloud Go+ track. Full tracks are only available to SoundCloud Go+ subscribers. Try accessing the track through the official SoundCloud website or app with a Go+ subscription, or look for a free version of this track.'}), 500
                            except ImportError:
                                # mutagen not available, skip duration check
                                pass
                            except Exception:
                                # Other errors, continue anyway
                                pass

                            download_successful = True
                            break

                    if download_successful:
                        break

                except Exception as e:
                    error_msg = str(e)
                    # Try next combination on known transient/selection errors.
                    if (
                        'Requested format is not available' in error_msg or
                        'HTTP Error 403' in error_msg or
                        'Forbidden' in error_msg
                    ):
                        continue
                    raise

            if download_successful:
                break

        if not download_successful:
            return jsonify({'error': 'Unable to find a compatible audio format for this content. The content might be restricted or unavailable.'}), 500

        if not os.path.exists(mp3_path):
            return jsonify({'error': 'Conversion failed. The content might be unavailable, private, age-restricted, or temporarily blocked.'}), 500

        # Final check for Go+ content in the downloaded file
        if is_soundcloud and not is_youtube_music:
            try:
                import mutagen
                from mutagen.mp3 import MP3
                audio = MP3(mp3_path)
                duration = audio.info.length
                if duration <= 35:  # Very short track, likely Go+ preview
                    return jsonify({'error': 'This track appears to be only 30 seconds long, which suggests it may be SoundCloud Go+ content. Full tracks are only available to SoundCloud Go+ subscribers. Try accessing the track through the official SoundCloud website or app with a Go+ subscription.'}), 500
            except ImportError:
                pass  # mutagen not available
            except Exception:
                pass  # Other errors, continue
        
        # Schedule file cleanup
        cleanup_file(mp3_path)
        
        return jsonify({
            'success': True,
            'filename': mp3_filename,
            'title': video_title,
            'download_url': f'/download/{mp3_filename}'
        })
        
    except Exception as e:
        error_msg = str(e)
        if 'Requested format is not available' in error_msg:
            return jsonify({'error': 'The requested audio format is not available for this video. This might be due to regional restrictions or the video being unavailable.'}), 500
        elif 'HTTP Error 403' in error_msg or 'Forbidden' in error_msg:
            return jsonify({'error': 'The platform blocked the request. Try again in a few minutes or try a different link.'}), 500
        elif 'HTTP Error 429' in error_msg:
            return jsonify({'error': 'Too many requests. Please wait a few minutes before trying again.'}), 500
        elif 'Video unavailable' in error_msg or 'Private video' in error_msg:
            return jsonify({'error': 'This content is unavailable, private, or restricted.'}), 500
        elif 'Sign in to confirm' in error_msg or 'age-restricted' in error_msg:
            return jsonify({'error': 'This content is age-restricted. Please sign in to the platform first and try again.'}), 500
        else:
            return jsonify({'error': f'An error occurred: {error_msg}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['TEMP_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found or has been cleaned up'}), 404
        
        # Get safe filename for download
        safe_filename = filename.replace('audio_', '').replace('.mp3', '') + '.mp3'
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype='audio/mpeg'
        )
        
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

if __name__ == '__main__':
    # Cleanup temp folder on startup
    if os.path.exists(TEMP_FOLDER):
        shutil.rmtree(TEMP_FOLDER)
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    
    app.run(debug=False, host='127.0.0.1', port=5000)
