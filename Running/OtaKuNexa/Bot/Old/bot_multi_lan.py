import re
import json
import asyncio
import os
import base64
import requests
from telethon import TelegramClient, events

# ================= TELEGRAM CONFIG =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
SESSION_NAME = "anime_indexer"

# Channels to scan
CHANNELS = [
    -1003175788400,
    -1003498912074
]

ADMIN_IDS = [8466952185] 

# ================= FILES =================
JSON_FILE = "anime_index.json"
STATE_FILE = "scan_state.json"

# ================= GITHUB CONFIG =================
# 🔴 PASTE YOUR TOKEN HERE
GITHUB_TOKEN = "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" 
GITHUB_OWNER = "ayarsbusiness-bot"
GITHUB_REPO = "anime-index"
GITHUB_BRANCH = "main"
GITHUB_FILE = "anime_index.json"

# ================= 1. SMART PARSER =================
class AnimeParser:
    def __init__(self):
        # 1. SPECIALS: Detect OVA/Special/Movies
        self.special_patterns = [
            r'(?i)(?:OVA|OAD)\s*[-_]?\s*(\d+)?', 
            r'(?i)(?:Special|SP)\s*[-_]?\s*(\d+)',
            r'(?i)Movie', r'(?i)NCED|NCOP'
        ]

        # 2. NOISE PATTERNS
        self.noise_patterns = [
            r'\[.*?\]', r'\(.*?\)',             # Brackets
            r'1080[pP]|720[pP]|480[pP]|4[kK]',  # Resolutions
            r'x264|x265|HEVC|AVC',              # Codecs
            r'10bit|Hi10|AAC|FLAC|DDP',         # Audio
            r'@\w+', r'www\.\w+\.\w+',          # Watermarks
            r'(?:19|20)\d{2}',                  # Years
            r'.mp4|.mkv|.avi'                   # Extensions
        ]

        # 3. EPISODE PATTERNS
        self.episode_patterns = [
            r'(?i)Ep\.*\s*(\d+)',           # Ep. 23
            r'(?i)E(\d+)',                  # E23
            r'[\s_]-[\s_](\d+)',            # " - 23 "
            r'(?:_|\s)(\d{1,3})(?:_|\s)',   # "_02_"
            r'[\s_](\d{1,3})$'              # Number at end
        ]

    def _normalize(self, text):
        if not text: return ""
        text = re.sub(r'(?i)Season\s*\d+', '', text)
        text = re.sub(r'(?i)S\d+', '', text)
        for pattern in self.noise_patterns:
            text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
        return text.strip()

    def parse(self, caption, file_name):
        sources = [file_name, caption]
        for source in sources:
            if not source: continue
            
            # Check Special
            for pat in self.special_patterns:
                m = re.search(pat, source)
                if m:
                    num = m.group(1) if m.groups() and m.group(1) else "1"
                    prefix = "OVA" if "ova" in m.group(0).lower() else "Special"
                    return 'special', f"{prefix}_{num}"

            # Check Episode
            clean_text = self._normalize(source)
            for pat in self.episode_patterns:
                m = re.search(pat, clean_text)
                if m:
                    try:
                        num = int(m.group(1))
                        if 0 < num < 2000: return 'episode', str(num)
                    except: continue
        
        return 'batch', None

# ================= 2. BATCHING & UTILS =================
def build_batches(episodes, unmatched):
    batches = {}
    if episodes:
        try:
            sorted_keys = sorted(episodes.keys(), key=lambda x: int(x))
            if sorted_keys:
                max_ep = int(sorted_keys[-1])
                total_batches = (max_ep + 4) // 5
                
                for b_idx in range(total_batches):
                    batch_num = b_idx + 1
                    start = (b_idx * 5) + 1
                    end = start + 4
                    current_batch = []
                    has_files = False
                    
                    for i in range(start, end + 1):
                        k = str(i)
                        if k in episodes:
                            current_batch.append(episodes[k])
                            has_files = True
                    
                    if has_files:
                        batches[f"batch{batch_num}"] = current_batch
        except Exception as e:
            print(f"Batch Error: {e}")
            if not unmatched: unmatched = []
            for k in episodes: unmatched.append(episodes[k])

    if unmatched: batches["batch_uncategorized"] = unmatched
    return batches

def natural_sort_key(key):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(key))]

def sort_dict_recursively(data):
    if isinstance(data, dict):
        sorted_items = sorted(data.items(), key=lambda item: natural_sort_key(item[0]))
        return {k: sort_dict_recursively(v) for k, v in sorted_items}
    elif isinstance(data, list): return data
    else: return data

# REGEX TAGS
TITLE_RE = re.compile(r"Title\s*:\s*(.+)", re.I)
SEASON_RE = re.compile(r"Season\s*:\s*(\d+)", re.I)
TOTAL_EP_RE = re.compile(r"Episode\s*:\s*(\d+)", re.I)
LANG_RE = re.compile(r"Language\s*:\s*(.+)", re.I)
MAL_ID_RE = re.compile(r"mal_id\s*:\s*(.+)", re.I)

UPDATE_PROGRESS = {"status": "idle", "processed": 0}

def load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(path, data):
    sorted_data = sort_dict_recursively(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)

def github_update_json(data):
    if not GITHUB_TOKEN or "YOUR_GITHUB" in GITHUB_TOKEN: return
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    
    sorted_data = sort_dict_recursively(data)
    content = json.dumps(sorted_data, indent=2, ensure_ascii=False)
    encoded = base64.b64encode(content.encode()).decode()
    
    payload = {"message": "auto update", "content": encoded, "branch": GITHUB_BRANCH}
    if sha: payload["sha"] = sha
    requests.put(url, headers=headers, json=payload)

# ================= 3. CORE LOGIC: FIND TITLE BY MAL ID =================
def find_title_by_mal_id(index, mal_ids_to_check, season_num):
    """
    Scans the entire DB to see if any existing Anime (in the same season)
    has one of the provided MAL IDs. 
    Returns the Existing Title if found, otherwise None.
    """
    if not mal_ids_to_check: return None
    
    target_ids = set(str(x) for x in mal_ids_to_check)
    
    for title, data in index.items():
        if "seasons" not in data: continue
        
        # Check specific season
        if season_num in data["seasons"]:
            season_data = data["seasons"][season_num]
            existing_ids = set(str(x) for x in season_data.get("mal_ids", []))
            
            # If intersection is not empty, we found a match!
            if not target_ids.isdisjoint(existing_ids):
                return title
                
    return None

# ================= 4. SAVE LOGIC (MULTI-LANG + ID MERGE) =================
def save_anime_to_index(anime_meta, episodes, specials, unmatched, index):
    if not anime_meta: return
    
    # 1. RESOLVE TITLE (MAL ID Priority)
    # Check if this MAL ID already exists in DB under a different name
    existing_title = find_title_by_mal_id(index, anime_meta["mal_ids"], anime_meta["season"])
    
    if existing_title:
        title = existing_title # Use the DB's title
        print(f"🔗 ID Match! Merging into existing: {title}")
    else:
        title = anime_meta["title"] # New Anime

    season = anime_meta["season"]
    lang = anime_meta["language"] or "Unknown"

    print(f"💾 Saving: {title} S{season} [{lang}]")

    # 2. Init Structure
    if title not in index: index[title] = {"seasons": {}}
    if season not in index[title]["seasons"]:
        index[title]["seasons"][season] = {
            "total_episodes": anime_meta["total"],
            "mal_ids": [],
            "languages": {}
        }
    
    season_node = index[title]["seasons"][season]

    # 3. SMART ID MERGE (Union of Old + New)
    existing_ids = set(str(x) for x in season_node.get("mal_ids", []))
    incoming_ids = set(str(x) for x in anime_meta.get("mal_ids", []))
    
    if incoming_ids:
        merged_ids = existing_ids.union(incoming_ids)
        season_node["mal_ids"] = sorted(list(merged_ids))

    # 4. Ensure Languages Dict
    if "languages" not in season_node: season_node["languages"] = {}

    # 5. Save Batches per Language
    final_batches = build_batches(episodes, unmatched)
    season_node["languages"][lang] = {
        "batches": final_batches,
        "specials": specials
    }

# ================= 5. SCANNER =================
async def scan_channel(client, channel_id, index, state, force_rescan=False):
    last_id = 0 if force_rescan else state.get(str(channel_id), 0)
    current_anime = None
    temp_ep = {}
    temp_sp = {}
    temp_un = [] 
    parser = AnimeParser()
    
    print(f"🚀 Scanning {channel_id} from {last_id}")

    async for msg in client.iter_messages(channel_id, min_id=last_id, reverse=True):
        text = msg.text or ""
        
        # --- START TAG ---
        if "</START>" in text:
            if current_anime:
                save_anime_to_index(current_anime, temp_ep, temp_sp, temp_un, index)
            
            title_m = TITLE_RE.search(text)
            season_m = SEASON_RE.search(text)
            lang_m = LANG_RE.search(text)
            total_m = TOTAL_EP_RE.search(text)
            mal_m = MAL_ID_RE.search(text)
            
            if title_m and season_m:
                mal_ids = [x.strip() for x in mal_m.group(1).split(',')] if mal_m else []
                
                current_anime = {
                    "title": title_m.group(1).strip(),
                    "season": season_m.group(1).strip(),
                    "language": lang_m.group(1).strip() if lang_m else "Unknown",
                    "total": int(total_m.group(1)) if total_m else 0,
                    "mal_ids": mal_ids
                }
                temp_ep, temp_sp, temp_un = {}, {}, []
                state[str(channel_id)] = msg.id
            continue

        # --- END TAG ---
        if "</End>" in text:
            if current_anime:
                save_anime_to_index(current_anime, temp_ep, temp_sp, temp_un, index)
                current_anime = None
                state[str(channel_id)] = msg.id
            continue

        # --- FILE HANDLING ---
        if current_anime and msg.file:
            fname = msg.file.name or ""
            cat, key = parser.parse(text, fname)
            entry = {"file": msg.id, "name": fname}
            
            if cat == 'episode':
                temp_ep[key] = entry
                UPDATE_PROGRESS["processed"] += 1
            elif cat == 'special':
                temp_sp[key] = entry
                UPDATE_PROGRESS["processed"] += 1
            else:
                temp_un.append(entry)
            
            state[str(channel_id)] = msg.id

    if current_anime:
        save_anime_to_index(current_anime, temp_ep, temp_sp, temp_un, index)
    
    save_json(STATE_FILE, state)

# ================= MAIN =================
async def main():
    index = load_json(JSON_FILE, {}) 
    state = load_json(STATE_FILE, {})
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    @client.on(events.NewMessage(pattern=r"/update(?:\s+(force))?"))
    async def update_handler(event):
        if event.sender_id not in ADMIN_IDS: return
        
        force = (event.pattern_match.group(1) == "force")
        await event.reply("☢️ Force Update..." if force else "🔄 Updating...")
        
        UPDATE_PROGRESS["processed"] = 0
        try:
            for ch in CHANNELS:
                await scan_channel(client, ch, index, state, force_rescan=force)
            
            save_json(JSON_FILE, index)
            github_update_json(index)
            await event.reply(f"✅ Done! Files: {UPDATE_PROGRESS['processed']}")
        except Exception as e:
            await event.reply(f"❌ Error: {e}")

    print("🤖 Bot Active. Send '/update force'")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())