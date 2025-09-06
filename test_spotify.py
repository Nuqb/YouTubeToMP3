#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
import re
import json

def extract_spotify_info(spotify_url):
    try:
        url_match = re.search(r'/track/([a-zA-Z0-9]+)', spotify_url)
        if url_match:
            track_id = url_match.group(1)
            print(f'Extracted Spotify track ID: {track_id}')

            embed_url = f'https://open.spotify.com/embed/track/{track_id}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://open.spotify.com/'
            }

            response = requests.get(embed_url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')

                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and ('entity' in script.string):
                        print(f'Found script with entity data, length: {len(script.string)}')
                        try:
                            json_start = script.string.find('{')
                            json_end = script.string.rfind('}') + 1

                            if json_start != -1 and json_end > json_start:
                                json_str = script.string[json_start:json_end]
                                data = json.loads(json_str)

                                if 'props' in data and 'pageProps' in data['props']:
                                    state = data['props']['pageProps'].get('state', {})
                                    entity_data = state.get('data', {}).get('entity', {})

                                    if entity_data.get('type') == 'track':
                                        track_name = entity_data.get('name')
                                        artists = entity_data.get('artists', [])
                                        if artists and len(artists) > 0:
                                            artist_name = artists[0].get('name')

                                            if track_name and artist_name:
                                                return track_name, artist_name

                        except json.JSONDecodeError:
                            name_match = re.search(r'"name"\s*:\s*"([^"]+)"', script.string)
                            if name_match:
                                track_name = name_match.group(1)
                                print(f'Found track name via regex: {track_name}')

                                artist_match = re.search(r'"artists"\s*:\s*\[\s*\{[^}]*"name"\s*:\s*"([^"]+)"', script.string)
                                if artist_match:
                                    artist_name = artist_match.group(1)
                                    print(f'Found artist name via regex: {artist_name}')
                                    return track_name, artist_name
                        except Exception as e:
                            print(f'Error parsing script: {e}')
                            continue

        return None, None

    except Exception as e:
        print(f'Error: {e}')
        return None, None

# Test with the user's URL
url = 'https://open.spotify.com/intl-fr/track/4S84adgZ72y8M4ebSZkn1S'
track_name, artist_name = extract_spotify_info(url)
print(f'\nResult: Track="{track_name}", Artist="{artist_name}"')
