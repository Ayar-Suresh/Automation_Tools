import yt_dlp
from tqdm import tqdm
import json, time, random

# 🎬 Keywords (your full list)
keywords = [
    # Romantic / Emotional
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


max_results_per_keyword = 200  # max results per keyword per batch
results = []

def fetch_videos_ytdlp(query, max_results=200):
    """Fetch videos for a keyword using yt_dlp, only include Shorts."""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True
    }
    batch = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            for entry in info.get('entries', []) or []:
                # Skip if duration is > 60s (not a Short)
                duration_sec = entry.get('duration', 0) or 0
                url = entry.get('webpage_url', '')
                
                # Some shorts may not have duration metadata, check URL for "/shorts/"
                if duration_sec > 60 and "/shorts/" not in url:
                    continue

                batch.append({
                    'videoId': entry.get('id'),
                    'title': entry.get('title'),
                    'creator': entry.get('uploader'),
                    'thumbnail': entry.get('thumbnail'),
                    'duration': duration_sec,
                    'url': url
                })
        except Exception as e:
            print(f"Error fetching '{query}': {e}")
    return batch

# 🚀 Start fetching
for kw in tqdm(keywords, desc="Fetching filtered anime shorts"):
    batch = fetch_videos_ytdlp(kw, max_results=max_results_per_keyword)
    results.extend(batch)
    time.sleep(random.uniform(0.8, 2.0))  # polite pause

# 🧹 Remove duplicates by videoId
unique = {v["videoId"]: v for v in results if v.get("videoId")}
final_list = list(unique.values())

# 💾 Save to JSON
with open("anime_shorts_filtered2026.json", "w", encoding="utf-8") as f:
    json.dump(final_list, f, ensure_ascii=False, indent=2)

print(f"\n✅ Saved {len(final_list)} high-quality anime shorts to anime_shorts_filtered.json")
