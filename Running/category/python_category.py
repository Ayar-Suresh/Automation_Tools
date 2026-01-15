import requests
import json
import time

BASE_URL = "https://api.jikan.moe/v4/anime/"

# -------------------------------
# CATEGORY → MAL ID LISTS (20 EACH)
# -------------------------------

# 1️⃣ Trending Anime in India
trending_anime_in_india_ids = [
    20,  # Naruto
    1735, # Naruto Shippuden
    21,   # One Piece
    40748, # Jujutsu Kaisen
    51009, # Solo Leveling
    16498, # Attack on Titan
    11665, # Demon Slayer
    34599, # Black Clover
    31964, # Mob Psycho 100
    32281, # Re:Zero
    1535,  # Death Note
    28977, # One Punch Man
    50265, # Chainsaw Man
    47917, # Hell's Paradise
    11061, # Hunter x Hunter
    5114,  # FMA Brotherhood
    9253,  # Steins Gate
    44042, # Blue Lock
    26055, # Haikyuu!!
    41025  # My Hero Academia S6
]

# 2️⃣ Popular Hindi Dubbed Anime
popular_hindi_dubbed_ids = [
    1535, 5114, 20, 1735, 21, 9253, 16498, 28977, 4654, 11061,
    34599, 34280, 20021, 457, 31043, 37349, 39551, 46976, 20583, 38000
]

# 3️⃣ OtakuNexa Top Picks
otakunexa_top_picks_ids = [
    11061, 1535, 5114, 9253, 40748, 50265, 51009, 28977, 31240, 40028,
    16498, 35839, 38000, 48413, 47164, 47257, 37521, 23273, 18679, 7472
]

# 4️⃣ Popular English Dubbed Anime
popular_english_dubbed_ids = [
    5114, 11061, 20, 1735, 21, 30276, 23273, 9253, 3588, 2167,
    31964, 37521, 2001, 28977, 38408, 38826, 33255, 39783, 40748, 41025
]

# 5️⃣ Hidden Gems
hidden_gems_ids = [
    32935, 32983, 22535, 41084, 37171, 36038, 32696, 24687, 38450, 37517,
    11757, 30694, 37105, 47778, 4632, 34798, 10087, 34561, 47917, 40750
]

# 6️⃣ Popular in India
popular_in_india_ids = [
    20, 21, 1535, 11061, 28977, 16498, 40748, 51009, 50265, 47917,
    44042, 26055, 11741, 10620, 34599, 34760, 23273, 31964, 32729, 24415
]

# 7️⃣ Top Picks for You (Mixed Recommendation)
top_picks_for_you_ids = [
    5114, 9253, 1535, 11061, 40221, 50321, 40748, 38408, 47164, 38234,
    20021, 31043, 38000, 14967, 31964, 50265, 44467, 51009, 3588, 4181
]

# 8️⃣ Evergreen Anime
evergreen_anime_ids = [
    20, 21, 5114, 1535, 11061, 9253, 457, 22319, 199, 19,
    33, 417, 27899, 34104, 16498, 28977, 35120, 38408, 28957, 3220
]

# 9️⃣ You May Also Like (Recommendation Style)
you_may_also_like_ids = [
    9253, 1535, 5114, 11061, 20021, 50265, 47917, 47164, 38000, 31043,
    31240, 14967, 31964, 39783, 41025, 40748, 44370, 41353, 24701, 31973
]

# 🔟 Anime from YouTube Recommendations
anime_from_yt_recommend_ids = [
    51009, 50265, 40748, 47917, 44511, 54560, 42916, 50321, 48316, 54789,
    37171, 41084, 51364, 54112, 40873, 40221, 51818, 47917, 48895, 54870
]

# 1️⃣1️⃣ Fantasy Anime
fantasy_anime_ids = [
    5114, 30276, 1535, 9253, 38000, 47164, 49828, 47917, 46420, 34096,
    48761, 33095, 43608, 38992, 31478, 2001, 31646, 16894, 42916, 40834
]

# 1️⃣2️⃣ Adventure Anime
adventure_anime_ids = [
    20, 21, 1735, 11061, 5114, 32281, 31964, 37105, 28977, 38000,
    38408, 50321, 40748, 51535, 47257, 47164, 4177, 34104, 42916, 42897
]


# -----------------------------------
# FUNCTION: Fetch + save JSON per category
# -----------------------------------

def fetch_anime_data(ids, filename):
    results = []

    for mal_id in ids:
        url = BASE_URL + str(mal_id)
        print(f"Fetching {mal_id} ...")
        r = requests.get(url)

        if r.status_code == 200:
            results.append(r.json())
        else:
            print(f"Failed: {mal_id}")
        
        time.sleep(0.7)  # prevent rate limit

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f"Saved → {filename}\n")


# -----------------------------------
# CATEGORY → FILE MAPPING
# -----------------------------------

categories = {
    "trending_anime_in_india.json": trending_anime_in_india_ids,
    "popular_hindi_dubbed.json": popular_hindi_dubbed_ids,
    "otakunexa_top_picks.json": otakunexa_top_picks_ids,
    "popular_english_dubbed.json": popular_english_dubbed_ids,
    "hidden_gems.json": hidden_gems_ids,
    "popular_in_india.json": popular_in_india_ids,
    "top_picks_for_you.json": top_picks_for_you_ids,
    "evergreen_anime.json": evergreen_anime_ids,
    "you_may_also_like.json": you_may_also_like_ids,
    "anime_from_yt_recommend.json": anime_from_yt_recommend_ids,
    "fantasy_anime.json": fantasy_anime_ids,
    "adventure_anime.json": adventure_anime_ids
}

# -----------------------------------
# RUN EVERYTHING
# -----------------------------------

for filename, ids in categories.items():
    fetch_anime_data(ids, filename)

print("ALL JSON FILES GENERATED SUCCESSFULLY.")
