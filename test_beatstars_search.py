#!/usr/bin/env python3

import yt_dlp

def search_youtube_beat(beat_name, producer_name):
    """Search for beat on YouTube and return the best match URL"""
    if not beat_name:
        return None

    try:
        # Beat-specific search queries (different from music tracks)
        search_queries = [
            f"{beat_name} beat instrumental",
            f"{beat_name} type beat",
            f"{producer_name} {beat_name} beat" if producer_name else f"{beat_name} beat",
            f"{beat_name} prod",
            f"{beat_name} beat free",
            f"{beat_name} instrumental beat"
        ]

        for search_query in search_queries:
            print(f"Trying search query: {search_query}")
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch5',  # Get top 5 results for beats
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    search_results = ydl.extract_info(f"ytsearch5:{search_query}", download=False)

                    if search_results and 'entries' in search_results and search_results['entries']:
                        print(f"Found {len(search_results['entries'])} results")

                        # Look for beat/instrumental content (avoid tutorials and vocal tracks)
                        for entry in search_results['entries']:
                            title = entry.get('title', '').lower()
                            description = entry.get('description', '').lower() if entry.get('description') else ''

                            print(f"Checking: {entry.get('title', '')}")

                            # Skip tutorial videos, vocal tracks, and non-beat content
                            skip_keywords = ['tutorial', 'how to', 'export', 'fl studio', 'logic pro', 'ableton', 'vocal', 'lyrics', 'singing', 'rap', 'hip hop']
                            if any(keyword in title or keyword in description for keyword in skip_keywords):
                                print(f"  Skipping (contains skip keywords): {title}")
                                continue

                            # Prefer beat/instrumental content
                            prefer_keywords = ['beat', 'instrumental', 'type beat', 'prod', 'producer', 'free beat', 'demo']
                            if any(keyword in title or keyword in description for keyword in prefer_keywords):
                                video_id = entry.get('id') or entry.get('url', '').split('/')[-1].split('?')[0]
                                print(f"  Found preferred beat match: {entry.get('title', '')}")
                                return f"https://www.youtube.com/watch?v={video_id}"

                        # If no preferred match found, return the first non-tutorial result
                        for entry in search_results['entries']:
                            title = entry.get('title', '').lower()
                            description = entry.get('description', '').lower() if entry.get('description') else ''

                            # Skip tutorials
                            if not any(keyword in title or keyword in description for keyword in ['tutorial', 'how to', 'export', 'fl studio']):
                                video_id = entry.get('id') or entry.get('url', '').split('/')[-1].split('?')[0]
                                print(f"  Using fallback beat match: {entry.get('title', '')}")
                                return f"https://www.youtube.com/watch?v={video_id}"

                except Exception as e:
                    print(f"Error with search query '{search_query}': {e}")
                    continue

    except Exception as e:
        print(f"Error searching YouTube for beat: {e}")

    return None

# Test the improved search
beat_name = "Plus Jamais"
producer_name = "Beatstars Producer"

print(f"Searching for beat: '{beat_name}' by '{producer_name}'")
result = search_youtube_beat(beat_name, producer_name)

if result:
    print(f"\n✅ Found YouTube URL: {result}")
else:
    print("\n❌ No suitable beat found")
