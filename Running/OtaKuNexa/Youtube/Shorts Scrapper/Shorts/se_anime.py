from googleapiclient.discovery import build
import json
import time
import random

# -------------------------
# CONFIGURATION
# -------------------------
API_KEY = "AIzaSyD3oS1Sfl8QTvZa2PSKzTxhIrMFECEk6r0"  # Replace with your key

# Reordered and expanded to prioritize "Sexy/Ecchi" as requested
KEYWORDS = [
    # --- PRIORITY: Mature / Ecchi / Sexy (Expanded) ---
    "Anime Ecchi Shorts 1080p", "Sexy Anime Waifu Edit", "Anime NSFW Moments Censored",
    "Anime Boing Boing Moments", "Anime Oppai Scene", "Ecchi Anime Harem Moments",
    "Anime Bath Scene Short", "Anime Beach Episode Clips", "Anime Fan Service Moments",
    "Anime Physics Jiggle", "Hot Anime Girl Edits 4K", "Anime Seduction Scene",
    "Anime Blush Moments", "Anime Thighs Edit", "Anime Maid Outfit Scene",
    "Hentai Style Anime Edit", "Anime Succubus Scene", "Anime Teacher Ecchi Moment",
    "Anime Nurse Outfit Edit", "Anime Bunny Girl Senpai Clips",
    "Anime Accidental Fall Ecchi", "Anime Skirt Flip Scene", "Anime Wet Clothes Scene",
    "Anime Hot Spring Moment", "Anime Changing Clothes Scene",
    "Mature Anime Romance Kiss", "Anime Kabedon Sexy Moment", "Anime Ear Licking ASMR Visual",
    
    # --- Action / Fight / Cool ---
    "Naruto Fight Short 1080p", "Demon Slayer Action AMV 4K", "Attack on Titan Short Clips",
    "One Piece Fight Short 1080p", "Tokyo Ghoul Fight Edit", "Jujutsu Kaisen Action Short",
    "Anime Battle AMV 1080p", "Epic Anime Fight Scene Short", "Anime Boss Fight Clip",
    "Anime Sword Fight Short", "Anime Power Up Scene AMV", "Chainsaw Man Action Short",
    "Bleach Bankai Moments Short", "Dragon Ball Z Fight 4K",
    
    # --- Romantic / Emotional ---
    "Romantic Anime Shorts", "Emotional Anime Scene Compilations", "Sad Anime Shorts",
    "Anime Love AMV 1080p", "Romantic Anime Edits", "Mature Love Anime Scene",
    "Anime Couples Short 1080p", "Anime Romantic Moments", "Anime Heartbreaking Scene",
    "Shoujo Anime Emotional Short", "Anime Confession Scene Short",
    
    # --- Trending / Mixed ---
    "Trending Anime Clips", "Popular Anime Shorts", "Top Anime AMV 1080p",
    "Viral Anime Short Clips", "Must Watch Anime Shorts", "Anime Funny Moments 1080p",
    "Anime Waifu Compilation", "Anime Best Girl Edit",
]

MAX_RESULTS_PER_KEYWORD = 50  # Max results per search
LIKE_THRESHOLD = 20000        # Lowered slightly to catch more niche/new viral content
OUTPUT_FILE = "filtered_anime_shorts.json"

# -------------------------
# INITIALIZE YOUTUBE API
# -------------------------
youtube = build('youtube', 'v3', developerKey=API_KEY)
high_quality_videos = []
video_ids_seen = set() # To avoid duplicates across keywords

# -------------------------
# MAIN LOOP
# -------------------------
print(f"🚀 Starting scrape for {len(KEYWORDS)} keywords...")

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
        print(f"⚠️ Error during search for '{kw}': {e}")
        continue

    # Extract IDs, ensuring no duplicates
    video_ids = []
    for item in search_res.get('items', []):
        vid = item['id']['videoId']
        if vid not in video_ids_seen:
            video_ids.append(vid)
            video_ids_seen.add(vid)

    if not video_ids:
        print("   No new videos found for this keyword.")
        continue

    # 2️⃣ Fetch video details (Stats + Status for Embedding)
    # Process in batches of 50
    for i in range(0, len(video_ids), 50):
        batch_ids = video_ids[i:i+50]
        try:
            # We request 'status' here to check embeddable
            stats_res = youtube.videos().list(
                id=",".join(batch_ids),
                part="snippet,statistics,status" 
            ).execute()
        except Exception as e:
            print(f"   ⚠️ Error fetching details: {e}")
            continue

        # 3️⃣ Filter by Likes AND Embeddable Status
        for v in stats_res.get('items', []):
            
            # --- CHECK 1: Is Embeddable? ---
            if not v['status']['embeddable']:
                continue  # Skip if not embeddable

            # --- CHECK 2: Is Popular? ---
            stats = v.get('statistics', {})
            likes = int(stats.get('likeCount', 0))
            views = int(stats.get('viewCount', 0))

            if likes >= LIKE_THRESHOLD:
                video_data = {
                    "videoId": v['id'],
                    "title": v['snippet']['title'],
                    "channel": v['snippet']['channelTitle'],
                    "likes": likes,
                    "views": views,
                    "embeddable": True,
                    "url": f"https://youtu.be/{v['id']}"
                }
                high_quality_videos.append(video_data)
                # print(f"   ✅ Added: {v['snippet']['title'][:40]}...")

    # 4️⃣ Polite pause to avoid quota issues
    time.sleep(random.uniform(0.5, 1.0))

# -------------------------
# SAVE TO JSON
# -------------------------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(high_quality_videos, f, ensure_ascii=False, indent=2)

print(f"\n✅ Saved {len(high_quality_videos)} videos to {OUTPUT_FILE}")