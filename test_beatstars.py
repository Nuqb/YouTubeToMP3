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
            print(f"Page content length: {len(response.content)}")
            print(f"First 500 chars: {response.content[:500].decode('utf-8', errors='ignore')}")

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

                # Look for producer/artist name
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
                        elif '-' in og_title:
                            parts = og_title.split('-', 1)
                            beat_title = parts[0].strip()
                            producer_name = parts[1].strip()
                            return beat_title, producer_name or "Unknown Producer"

                # Look for JSON data in scripts
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string:
                        # Look for beat data in JSON
                        if 'beat' in script.string.lower() or 'producer' in script.string.lower():
                            print(f"Found script with potential beat data: {script.string[:200]}...")

                # Look for h1 tags that might contain the beat title
                h1_tags = soup.find_all('h1')
                for h1 in h1_tags:
                    if h1.string and len(h1.string.strip()) > 3:
                        beat_title = h1.string.strip()
                        print(f"Found H1 title: {beat_title}")
                        return beat_title, "Beatstars Producer"

                # If we found a title but no producer, return just the title
                if title_text:
                    return title_text, "Beatstars Producer"

        # Fallback: extract from URL slug
        if beat_slug:
            beat_name = beat_slug.replace('-', ' ').title()
            return beat_name, "Beatstars Producer"

        return f"Beatstars Beat {beat_id}", "Beatstars Producer"

    except Exception as e:
        print(f"Error extracting Beatstars info: {e}")
        return None, None

# Test with Beatstars URLs
beatstars_urls = [
    'https://www.beatstars.com/beat/plus-jamais-21847271',
    'https://www.beatstars.com/beat/21847271'
]

for url in beatstars_urls:
    beat_name, producer_name = extract_beatstars_info(url)
    print(f'\nBeatstars Result for {url}: Beat="{beat_name}", Producer="{producer_name}"')
