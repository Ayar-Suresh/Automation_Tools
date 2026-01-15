from googleapiclient.discovery import build
import json
import time
import random

# -------------------------
# CONFIGURATION
# -------------------------
API_KEY = "AIzaSyD3oS1Sfl8QTvZa2PSKzTxhIrMFECEk6r0"  # replace with your YouTube Data API v3 key
KEYWORDS = [   # Romantic / Emotional
    "Romantic Anime Shorts", "Emotional Anime Scene Compilations", "Sad Anime Shorts",
    "Anime Love AMV 1080p", "Romantic Anime Edits", "Mature Love Anime Scene",
    "Anime Couples Short 1080p", "Anime Romantic Moments", "Anime Heartbreaking Scene",
    "Shoujo Anime Emotional Short", "Anime Confession Scene Short",
    
    # Action / Fight / AMV
    "Naruto Fight Short 1080p", "Demon Slayer Action AMV 4K", "Attack on Titan Short Clips",
    "One Piece Fight Short 1080p", "Tokyo Ghoul Fight Edit", "Jujutsu Kaisen Action Short",
    "Anime Battle AMV 1080p", "Epic Anime Fight Scene Short", "Anime Boss Fight Clip",
    "Anime Sword Fight Short", "Anime Power Up Scene AMV",
    
    # Language Specific
    "Anime Shorts Hindi", "Anime AMV Hindi 1080p", "One Piece Hindi AMV",
    "Naruto Hindi Short 1080p", "Demon Slayer Hindi Clip", "Jujutsu Kaisen Hindi Short",
    
    # Japanese / Original
    "Anime Shorts Japanese", "Romantic Anime Japanese Short", "Emotional Anime Japanese Scene",
    "Shonen Anime Japanese Short", "Shoujo Anime Japanese AMV",
    
    # Mature / Adult / Sexy
    "Hentai Anime Clips", "NSFW Anime Shorts", "Adult Anime Scene Compilations",
    "Erotic Anime Shorts", "Ecchi Anime Short 1080p", "Mature Anime Erotic Scene",
    "Sexy Anime Girl Short Clip", "Anime Bedroom Scene Short", "Anime Kiss Scene NSFW",
    "Anime Ecchi Edits", "Anime Adult AMV 1080p",
    
    # Old / Classic / Nostalgia
    "Old Anime Shorts", "Classic Anime AMV", "Vintage Anime Scene Short",
    "Retro Anime Clip 1080p", "Anime 90s Short", "Anime Old School AMV",
    
    # Trending / Popular
    "Trending Anime Clips", "Popular Anime Shorts", "Top Anime AMV 1080p",
    "Viral Anime Short Clips", "Must Watch Anime Shorts",
    
    # Specific Characters / Shows
    "Naruto Romantic Short", "Sakura Emotional Scene Short", "Luffy Fight Short 1080p",
    "Nezuko Demon Slayer AMV", "Itachi Naruto Short Clip", "Gojo Jujutsu Kaisen Short",
    
    # Variety / Mixed
    "Anime Sad AMV 1080p", "Anime Comedy Short Clip", "Funny Anime Short 1080p",
    "Anime Slice of Life Short", "Anime School Scene Short", "Anime Drama AMV 1080p",
    
    # More Sexy / Adult / Ecchi Variations
    "Ecchi Anime Compilation", "NSFW Anime AMV 1080p", "Sexy Anime Girl AMV",
    "Hentai Anime 1080p Short", "Anime Adult Scene Compilation", "Anime Ecchi Short Video",
    
    # Additional High-Quality Keywords
    "Anime Short 1080p", "Anime AMV 4K", "Anime Emotional Short", "Anime Edit Short",
    "Anime Fight Scene Clip", "Anime Action AMV 1080p", "Anime Shonen Short", "Anime Shoujo Short",
]
MAX_RESULTS_PER_KEYWORD = 50  # maximum allowed per API call
LIKE_THRESHOLD = 50000        # minimum likes to consider as "highly liked"
OUTPUT_FILE = "highly_liked_anime_shorts.json"

# -------------------------
# INITIALIZE YOUTUBE API
# -------------------------
youtube = build('youtube', 'v3', developerKey=API_KEY)
high_quality_videos = []

# -------------------------
# MAIN LOOP
# -------------------------
for kw in KEYWORDS:
    print(f"\n🔍 Searching for: {kw}")

    # 1️⃣ Search videos (Shorts only)
    try:
        search_res = youtube.search().list(
            q=kw,
            type="video",
            videoDuration="short",  # Only shorts (<4 minutes)
            part="id",
            maxResults=MAX_RESULTS_PER_KEYWORD
        ).execute()
    except Exception as e:
        print(f"Error during search for '{kw}': {e}")
        continue

    video_ids = [item['id']['videoId'] for item in search_res.get('items', [])]
    if not video_ids:
        print("No videos found for this keyword.")
        continue

    # 2️⃣ Fetch video statistics in batches
    for i in range(0, len(video_ids), 50):
        batch_ids = video_ids[i:i+50]
        try:
            stats_res = youtube.videos().list(
                id=",".join(batch_ids),
                part="snippet,statistics"
            ).execute()
        except Exception as e:
            print(f"Error fetching stats for batch: {e}")
            continue

        # 3️⃣ Filter by like count
        for v in stats_res.get('items', []):
            stats = v.get('statistics', {})
            likes = int(stats.get('likeCount', 0))
            views = int(stats.get('viewCount', 0))
            if likes >= LIKE_THRESHOLD:
                high_quality_videos.append({
                    "videoId": v['id'],
                    "title": v['snippet']['title'],
                    "channel": v['snippet']['channelTitle'],
                    "likes": likes,
                    "views": views,
                    "url": f"https://youtu.be/{v['id']}"
                })

    # 4️⃣ Polite pause to avoid quota issues
    time.sleep(random.uniform(0.5, 1.5))

# -------------------------
# SAVE TO JSON
# -------------------------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(high_quality_videos, f, ensure_ascii=False, indent=2)

print(f"\n✅ Saved {len(high_quality_videos)} highly liked anime shorts to {OUTPUT_FILE}")
