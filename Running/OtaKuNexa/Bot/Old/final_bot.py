import re
import json
import asyncio
import os
import base64
import requests
from telethon import TelegramClient, events
from telethon.tl.types import Message

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

# ================= 1. SMART PARSER (LOGIC: FILENAME > CAPTION) =================
class AnimeParser:
    def __init__(self):
        # 1. SPECIALS: Detect OVA/Special/Movies
        self.special_patterns = [
            r'(?i)(?:OVA|OAD)\s*[-_]?\s*(\d+)?', 
            r'(?i)(?:Special|SP)\s*[-_]?\s*(\d+)',
            r'(?i)Movie', r'(?i)NCED|NCOP'
        ]

        # 2. NOISE PATTERNS: Strip these out to avoid false positives
        self.noise_patterns = [
            r'\[.*?\]', r'\(.*?\)',             # Brackets like [1080p]
            r'1080[pP]|720[pP]|480[pP]|4[kK]',  # Resolutions
            r'x264|x265|HEVC|AVC',              # Codecs
            r'10bit|Hi10|AAC|FLAC|DDP',         # Audio
            r'@\w+', r'www\.\w+\.\w+',          # Watermarks/URLs
            r'(?:19|20)\d{2}',                  # Years (1999, 2024) - Don't match as episode!
            r'.mp4|.mkv|.avi'                   # Extensions
        ]

        # 3. EPISODE PATTERNS (Priority Order)
        self.episode_patterns = [
            # Explicit Labels
            r'(?i)Ep\.*\s*(\d+)',           # Ep. 23
            r'(?i)E(\d+)',                  # E23
            r'[\s_]-[\s_](\d+)',            # " - 23 "
            
            # 🔥 CRITICAL FIX: Standalone number surrounded by underscores or spaces
            # Matches: "_02_", " 02 ", "_23_"
            # Does NOT match: "2024" (because of year filter above)
            r'(?:_|\s)(\d{1,3})(?:_|\s)',
            
            # Fallback: Number at the very end of the string
            r'[\s_](\d{1,3})$'
        ]

    def _normalize(self, text):
        if not text: return ""
        
        # 1. Remove Season info FIRST so "Season 2" doesn't become Ep 2
        text = re.sub(r'(?i)Season\s*\d+', '', text)
        text = re.sub(r'(?i)S\d+', '', text)
        
        # 2. Remove technical noise
        for pattern in self.noise_patterns:
            text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
            
        return text.strip()

    def parse(self, caption, file_name):
        # Priority: Check Filename first (usually cleaner), then Caption
        sources = [file_name, caption] 
        
        for source in sources:
            if not source: continue

            # A. Check Special
            for pat in self.special_patterns:
                m = re.search(pat, source)
                if m:
                    num = m.group(1) if m.groups() and m.group(1) else "1"
                    prefix = "OVA" if "ova" in m.group(0).lower() else "Special"
                    return 'special', f"{prefix}_{num}"

            # B. Check Episode
            clean_text = self._normalize(source)
            for pat in self.episode_patterns:
                m = re.search(pat, clean_text)
                if m:
                    try:
                        num = int(m.group(1))
                        # Basic Sanity Check: Episode 0-2000
                        if 0 < num < 2000: return 'episode', str(num)
                    except: continue
        
        # C. Failed? It goes to Uncategorized
        return 'batch', None

# ================= 2. STRICT BATCHING (1-5, 6-10) =================
def build_batches(episodes, unmatched):
    batches = {}
    if episodes:
        try:
            sorted_keys = sorted(episodes.keys(), key=lambda x: int(x))
            if sorted_keys:
                max_ep = int(sorted_keys[-1])
                # Calculate required batches (e.g. Ep 23 needs 5 batches)
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
                    
                    # Only add batch if it has at least one file
                    if has_files:
                        batches[f"batch{batch_num}"] = current_batch

        except Exception as e:
            print(f"Batch Error: {e}")
            if not unmatched: unmatched = []
            for k in episodes: unmatched.append(episodes[k])

    if unmatched: batches["batch_uncategorized"] = unmatched
    return batches

# ================= 3. UTILS =================
def natural_sort_key(key):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(key))]

def sort_dict_recursively(data):
    if isinstance(data, dict):
        sorted_items = sorted(data.items(), key=lambda item: natural_sort_key(item[0]))
        return {k: sort_dict_recursively(v) for k, v in sorted_items}
    elif isinstance(data, list): return data
    else: return data

# REGEX FOR TAGS
TITLE_RE = re.compile(r"Title\s*:\s*(.+)", re.I)
SEASON_RE = re.compile(r"Season\s*:\s*(\d+)", re.I)
TOTAL_EP_RE = re.compile(r"Episode\s*:\s*(\d+)", re.I)
LANG_RE = re.compile(r"Language\s*:\s*(.+)", re.I)
MAL_ID_RE = re.compile(r"mal_id\s*:\s*(.+)", re.I)

UPDATE_RUNNING = False
UPDATE_PROGRESS = {"status": "idle", "current_channel": None, "processed": 0, "failed": 0}

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
    if not GITHUB_TOKEN or "YOUR_GITHUB" in GITHUB_TOKEN:
        print("❌ ERROR: GitHub Token missing.")
        return

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    
    sorted_data = sort_dict_recursively(data)
    content = json.dumps(sorted_data, indent=2, ensure_ascii=False)
    encoded = base64.b64encode(content.encode()).decode()
    
    payload = {
        "message": "auto update anime index",
        "content": encoded,
        "branch": GITHUB_BRANCH
    }
    if sha: payload["sha"] = sha
    
    res = requests.put(url, headers=headers, json=payload)
    if res.status_code not in [200, 201]:
        raise Exception(f"GitHub Error: {res.text}")

# ================= 4. SAVE LOGIC (PRESERVES MAL_IDS & CONFIG) =================
def save_anime_to_index(anime_meta, episodes, specials, unmatched, index):
    if not anime_meta: return
    print(f"💾 Saving: {anime_meta['title']} Season {anime_meta['season']}...")
    
    title = anime_meta["title"]
    season = anime_meta["season"]
    
    if title not in index: index[title] = {"seasons": {}}
    
    # --- PRESERVATION LOGIC ---
    # 1. Try to get existing data from JSON to keep mal_ids
    existing_data = {}
    if season in index[title]["seasons"]:
        existing_data = index[title]["seasons"][season]
    
    # 2. If new mal_ids found in tag, use them. If not, keep old ones.
    final_mal_ids = anime_meta.get("mal_ids", [])
    if not final_mal_ids:
        final_mal_ids = existing_data.get("mal_ids", [])

    # 3. Build new batches from Telegram files
    final_batches = build_batches(episodes, unmatched)
    
    season_data = {
        "language": anime_meta["language"],
        "total_episodes": anime_meta["total"],
        "mal_ids": final_mal_ids,  # Preserved or Updated
        "batches": final_batches,
        "specials": specials
    }
    
    index[title]["seasons"][season] = season_data

# ================= 5. SCANNER (START-TO-START) =================
async def scan_channel(client, channel_id, index, state, force_rescan=False):
    # FORCE RESCAN: If true, ignore saved ID and scan from 0
    last_id = 0 if force_rescan else state.get(str(channel_id), 0)
    
    UPDATE_PROGRESS["current_channel"] = channel_id
    current_anime = None
    temp_episodes = {}
    temp_specials = {}
    temp_unmatched = [] 
    parser = AnimeParser()
    
    print(f"🚀 Scanning {channel_id} from ID {last_id}")

    async for msg in client.iter_messages(channel_id, min_id=last_id, reverse=True):
        text = msg.text or ""
        
        # 1. START TAG detected -> Save OLD, Start NEW
        if "</START>" in text:
            if current_anime:
                print(f"🔄 New Start. Saving previous: {current_anime['title']}")
                save_anime_to_index(current_anime, temp_episodes, temp_specials, temp_unmatched, index)
            
            title_m = TITLE_RE.search(text)
            season_m = SEASON_RE.search(text)
            lang_m = LANG_RE.search(text)
            total_m = TOTAL_EP_RE.search(text)
            mal_m = MAL_ID_RE.search(text)
            
            if title_m and season_m:
                # Parse MAL IDs if present in tag
                mal_ids = []
                if mal_m:
                    mal_ids = [x.strip() for x in mal_m.group(1).split(',') if x.strip()]

                current_anime = {
                    "title": title_m.group(1).strip(),
                    "season": season_m.group(1).strip(),
                    "language": lang_m.group(1).strip() if lang_m else "Unknown",
                    "total": int(total_m.group(1)) if total_m else 0,
                    "mal_ids": mal_ids
                }
                # Reset containers
                temp_episodes = {}
                temp_specials = {}
                temp_unmatched = []
                
                print(f"🔹 Started: {current_anime['title']} S{current_anime['season']}")
                state[str(channel_id)] = msg.id
            continue

        # 2. END TAG detected (Optional explicit close)
        if "</End>" in text:
            if current_anime:
                print(f"🔸 Explicit End: {current_anime['title']}")
                save_anime_to_index(current_anime, temp_episodes, temp_specials, temp_unmatched, index)
                current_anime = None 
                state[str(channel_id)] = msg.id
            continue

        # 3. FILE detected -> Add to current anime
        if current_anime and msg.file:
            file_name = msg.file.name or ""
            category, key = parser.parse(text, file_name)
            
            file_entry = {"file": msg.id, "name": file_name}
            
            if category == 'episode':
                temp_episodes[key] = file_entry
                UPDATE_PROGRESS["processed"] += 1
            elif category == 'special':
                temp_specials[key] = file_entry
                UPDATE_PROGRESS["processed"] += 1
            else:
                temp_unmatched.append(file_entry)
                UPDATE_PROGRESS["failed"] += 1
            
            state[str(channel_id)] = msg.id

    # 4. End of Loop -> Save whatever was pending
    if current_anime:
        print(f"🏁 Channel End. Saving final: {current_anime['title']}")
        save_anime_to_index(current_anime, temp_episodes, temp_specials, temp_unmatched, index)
    
    save_json(STATE_FILE, state)

# ================= MAIN BOT =================
async def main():
    global UPDATE_RUNNING
    # Load existing JSON to preserve 'config' and other non-scanned data
    index = load_json(JSON_FILE, {}) 
    state = load_json(STATE_FILE, {})
    
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    @client.on(events.NewMessage(pattern=r"/update(?:\s+(force))?"))
    async def update_handler(event):
        global UPDATE_RUNNING
        if event.sender_id not in ADMIN_IDS: return
        if UPDATE_RUNNING: return await event.reply("⚠️ Busy...")

        force_mode = False
        if event.pattern_match.group(1) == "force":
            force_mode = True
            await event.reply("☢️ FORCE MODE: Rescanning ALL history (Start-to-Start)...")
        else:
            await event.reply("🔄 Checking for NEW files...")

        UPDATE_RUNNING = True
        UPDATE_PROGRESS.update({"status": "starting", "processed": 0, "failed": 0})

        try:
            for ch in CHANNELS:
                UPDATE_PROGRESS["status"] = "scanning"
                await scan_channel(client, ch, index, state, force_rescan=force_mode)

            UPDATE_PROGRESS["status"] = "saving"
            save_json(JSON_FILE, index)
            
            if GITHUB_TOKEN and "YOUR_GITHUB" not in GITHUB_TOKEN:
                UPDATE_PROGRESS["status"] = "uploading"
                github_update_json(index)
                await event.reply(f"✅ Success! Processed {UPDATE_PROGRESS['processed']} files.")
            else:
                await event.reply("✅ Local Save Only (Token missing).")

        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
            print(f"ERROR: {e}")
        finally:
            UPDATE_RUNNING = False

    @client.on(events.NewMessage(pattern="/status"))
    async def status_handler(event):
        if event.sender_id not in ADMIN_IDS: return
        await event.reply(f"📊 {UPDATE_PROGRESS['status']} | Files: {UPDATE_PROGRESS['processed']}")

    print("🤖 Bot Active. Send '/update force' to fix missed files.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())