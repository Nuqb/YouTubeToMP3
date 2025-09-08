#!/usr/bin/env python3

import yt_dlp

def search_youtube_beat_simple(search_query, search_type):
    """Simple YouTube search for beats - returns first non-tutorial result"""
    try:
        print(f"Searching for: {search_query}")
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch5',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(f"ytsearch5:{search_query}", download=False)

            if search_results and 'entries' in search_results and search_results['entries']:
                print(f"Found {len(search_results['entries'])} results")
                # Return the first non-tutorial result
                for entry in search_results['entries']:
                    title = entry.get('title', '').lower()
                    description = entry.get('description', '').lower() if entry.get('description') else ''

                    print(f"  Checking: {entry.get('title', '')}")

                    # Skip tutorials
                    if not any(keyword in title or keyword in description for keyword in ['tutorial', 'how to', 'export', 'fl studio']):
                        video_id = entry.get('id') or entry.get('url', '').split('/')[-1].split('?')[0]
                        print(f"  ✅ Selected: {entry.get('title', '')}")
                        return f"https://www.youtube.com/watch?v={video_id}"
                    else:
                        print(f"  ❌ Skipped (tutorial): {entry.get('title', '')}")

    except Exception as e:
        print(f"Error in simple beat search: {e}")

    return None

# Test the searches that should work
test_searches = [
    "Plus Jamais layton",
    "Plus Jamais instrumental",
    "Plus Jamais beat"
]

print("Testing searches for 'Plus Jamais' beat...")
print("=" * 50)

for search in test_searches:
    print(f"\n🔍 Testing: {search}")
    result = search_youtube_beat_simple(search, "direct")
    if result:
        print(f"✅ Found: {result}")
        # Check if it's the correct video (Y7wWyy8By_U)
        if "Y7wWyy8By_U" in result:
            print("🎯 PERFECT! Found the exact video the user wants!")
            break
    else:
        print("❌ No suitable result found")
    print("-" * 30)
