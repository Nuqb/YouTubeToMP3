import os
import tempfile
import shutil
from flask import Flask, render_template, request, send_file, jsonify, after_this_request
import yt_dlp
import threading
import time
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# Configure upload folder for temporary files
TEMP_FOLDER = tempfile.mkdtemp()
app.config['TEMP_FOLDER'] = TEMP_FOLDER

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

        # Validate URL (YouTube, YouTube Music, SoundCloud, or Spotify)
        if not (('youtube.com' in url or 'youtu.be' in url or 'music.youtube.com' in url) or ('soundcloud.com' in url) or ('spotify.com' in url or 'open.spotify.com' in url)):
            return jsonify({'error': 'Please provide a valid YouTube, YouTube Music, SoundCloud, or Spotify URL'}), 400
        
        # Handle Spotify URLs by finding the track on YouTube
        original_url = url
        is_spotify = 'spotify.com' in url or 'open.spotify.com' in url

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
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best',
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
        }

        # Platform-specific optimizations
        if is_youtube_music:
            # YouTube Music - use YouTube settings but with Music domain
            platform_opts = {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://music.youtube.com/',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
            }
        elif is_soundcloud:
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
            # YouTube-specific settings
            platform_opts = {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
            }

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
            'bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best',
            'bestaudio/best[height<=480]/best[height<=480]',  # Lower quality fallback
            'best'  # Ultimate fallback
        ]

        for format_option in format_options:
            try:
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
                    else:
                        # Try to find any audio file that might have been created
                        temp_dir = app.config['TEMP_FOLDER']
                        for file in os.listdir(temp_dir):
                            if file.startswith(f"audio_{timestamp}") and file.endswith(('.mp3', '.m4a', '.webm')):
                                # Rename to mp3 if needed
                                old_path = os.path.join(temp_dir, file)
                                if not file.endswith('.mp3'):
                                    os.rename(old_path, mp3_path)
                                download_successful = True
                                break

            except Exception as e:
                error_msg = str(e)
                if 'Requested format is not available' in error_msg:
                    continue  # Try next format option
                else:
                    raise e  # Re-raise non-format related errors

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
    
    app.run(debug=True, host='0.0.0.0', port=5000) 