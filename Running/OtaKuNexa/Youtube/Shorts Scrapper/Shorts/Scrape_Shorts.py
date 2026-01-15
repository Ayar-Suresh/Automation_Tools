from youtubesearchpython import VideosSearch

from tqdm import tqdm
import json, time, random, re

# 🎬 Smart keywords
keywords = [
    "Romantic Anime Shorts", "Emotional Anime Scene Compilations", "Sad Anime Shorts", "Mature Anime Clips",
    "anime shorts 1080p", "anime amv 4k", "anime scenes Hindi", "boruto anime shorts",
    "Trending Anime Clips", "Romantic Anime Edits", "Mature Love Anime Scene",
    "anime shorts Japanese", "anime fight edit", "anime emotional scene",
    "Naruto short 1080p", "Demon Slayer edit 4K", "Attack on Titan shorts",
    "One Piece Hindi anime", "Tokyo Ghoul edit", "Jujutsu Kaisen shorts"
]

max_results_per_keyword = 400
results = []

def is_high_quality(video):
    """Filter out low-quality or unrelated videos."""
    title = video.get("title", "").lower()
    desc = video.get("descriptionSnippet", [{}])[0].get("text", "").lower() if video.get("descriptionSnippet") else ""

    # Keywords indicating quality or desired language
    if not any(x in title or x in desc for x in ["anime", "amv", "edit", "short"]):
        return False
    if any(x in title for x in ["reaction", "meme", "funny", "gameplay"]):
        return False
    if any(x in title for x in ["1080", "4k", "official", "amv", "edit", "short"]):
        return True
    return False

def fetch_videos(query, limit=20):
    """Fetch a batch of videos for a given query."""
    vs = VideosSearch(query, limit=limit)
    data = vs.result().get('result', [])
    videos = []
    for v in data:
        if not is_high_quality(v):
            continue
        videos.append({
            "videoId": v.get("id"),
            "title": v.get("title"),
            "creator": v["channel"]["name"] if "channel" in v else "",
            "thumbnail": v["thumbnails"][0]["url"] if v.get("thumbnails") else "",
        })
    return videos

# 🚀 Start fetching
for kw in tqdm(keywords, desc="Fetching filtered anime shorts"):
    count = 0
    while count < max_results_per_keyword:
        try:
            batch = fetch_videos(kw, limit=20)
            if not batch:
                break
            results.extend(batch)
            count += len(batch)
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"Error fetching for {kw}: {e}")
            break

# 🧹 Remove duplicates
unique = {v["videoId"]: v for v in results if v.get("videoId")}
final_list = list(unique.values())

# 💾 Save
with open("anime_shorts_filtered.json", "w", encoding="utf-8") as f:
    json.dump(final_list, f, ensure_ascii=False, indent=2)

print(f"\n✅ Saved {len(final_list)} high-quality anime shorts to anime_shorts_filtered.json")
