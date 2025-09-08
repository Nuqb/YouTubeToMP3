#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
import re

def extract_beatstars_info(beatstars_url):
    """Extract beat information from Beatstars URL"""
    try:
        # Extract beat ID from URL
        url_match = re.search(r'/beat(?:/([^/]+)-)?(\d+)', beatstars_url)
        if not url_match:
            return None, None

        beat_slug = url_match.group(1)
        beat_id = url_match.group(2)
        print(f"Extracted Beatstars beat ID: {beat_id}, slug: {beat_slug}")

        # Try to get beat information from the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.beatstars.com/'
        }

        response = requests.get(beatstars_url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for beat title in various places
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                title_text = title_tag.string.strip()
                print(f"Found title from Beatstars: {title_text}")

                # Check if this is a generic Beatstars page (not a specific beat)
                if "Buy Beats Online" in title_text or "Download Beats" in title_text:
                    print("This appears to be a generic Beatstars page, extracting from URL slug")
                    # Extract beat name from URL slug
                    if beat_slug:
                        beat_name = beat_slug.replace('-', ' ').title()
                        return beat_name, "Beatstars Producer"
                    else:
                        return f"Beatstars Beat {beat_id}", "Beatstars Producer"

                # Clean up title (remove "Beatstars -" prefix, etc.)
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

        # Fallback: extract from URL slug
        if beat_slug:
            beat_name = beat_slug.replace('-', ' ').title()
            return beat_name, "Beatstars Producer"

        return f"Beatstars Beat {beat_id}", "Beatstars Producer"

    except Exception as e:
        print(f"Error extracting Beatstars info: {e}")
        return None, None

# Test with the user's Beatstars URL
beatstars_url = 'https://www.beatstars.com/beat/plus-jamais-21847271'
print(f"Testing Beatstars URL: {beatstars_url}")
beat_name, producer_name = extract_beatstars_info(beatstars_url)
print(f"\nExtracted: Beat='{beat_name}', Producer='{producer_name}'")
