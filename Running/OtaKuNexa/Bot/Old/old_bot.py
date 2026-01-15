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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = "OtakuNexa"
GITHUB_REPO = "anime-index"
GITHUB_BRANCH = "main"
GITHUB_FILE = "anime_index.json"

# ================= 1. ROBUST PARSER =================
class AnimeParser:
    def __init__(self):
        # 1. SPECIALS: Detect OVA/Special
        self.special_patterns = [
            r'(?i)(?:OVA|OAD)\s*[-_]?\s*(\d+)?', 
            r'(?i)(?:Special|SP)\s*[-_]?\s*(\d+)'
        ]

        # 2. NOISE: Remove things that look like numbers but aren't
        self.noise_patterns = [
            r'1080[pP]', r'720[pP]', r'480[pP]', r'4[kK]',  # Resolutions
            r'x264', r'x265', r'HEVC', r'AVC',              # Codecs
            r'10bit', r'Hi10', r'AAC', r'FLAC',             # Audio
            r'(?:19|20)\d{2}',                              # Years (2024)
            r'@\w+',                                        # Watermarks
            r'\[([a-fA-F0-9]{8})\]'                         # CRC32 Checksums like [A1B2C3D4]
        ]

        # 3. EPISODE NUMBERS: Ordered by "Strictness"
        self.episode_patterns = [
            # High Priority: [S1-01] or S01E01
            r'\[S\d+-(\d+)\]',
            r'(?i)s\d+e(\d+)',
            
            # Contextual: "Season 2 05" (Handle the underscore issue via normalization)
            r'(?i)Season\s*\d+[\s_]+(\d+)',
            
            # Explicit: "Episode 5"
            r'(?i)(?:episode|ep|ep\.)\s*(\d+)',
            
            # Loose (Only works if text is clean): " - 05 " or " 05.mkv"
            r'\s-\s+(\d+)\s',
            r'[\s_](\d+)(?=\.\w{3,4}$)'
        ]

    def _normalize(self, text):
        """Prepares text for regex: converts underscores to spaces, removes noise."""
        if not text: return ""
        # 1. Underscores to spaces (Fixes: Season_2_01)
        text = text.replace('_', ' ')
        
        # 2. Remove Noise
        for pattern in self.noise_patterns:
            text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
        
        # 3. Collapse spaces
        return re.sub(r'\s+', ' ', text).strip()

    def parse(self, caption, file_name):
        """
        Returns: (Category, Key)
        """
        # Strategy: Prefer Caption, Fallback to Filename
        sources = [caption, file_name]
        
        for source in sources:
            if not source: continue

            # A. Check Special
            for pat in self.special_patterns:
                m = re.search(pat, source)
                if m:
                    num = m.group(1) if m.group(1) else "1"
                    prefix = "OVA" if "ova" in m.group(0).lower() else "Special"
                    return 'special', f"{prefix}_{num}"

            # B. Check Episode (Cleaned)
            clean_text = self._normalize(source)
            for pat in self.episode_patterns:
                m = re.search(pat, clean_text)
                if m:
                    try:
                        num = int(m.group(1))
                        if 0 < num < 2000: return 'episode', str(num)
                    except: continue
        
        # If nothing found in either caption or filename:
        return 'batch', None

# ================= 2. SAFE BATCHING LOGIC =================
def build_batches(episodes, unmatched):
    """
    episodes: Dict {"1": {...}, "2": {...}}
    unmatched: List [{...}, {...}]
    """
    batches = {}
    
    # 1. Process CLEAN episodes (1-5, 6-10)
    if episodes:
        # Convert keys to int for sorting
        try:
            sorted_keys = sorted(episodes.keys(), key=lambda x: int(x))
            if sorted_keys:
                max_ep = int(sorted_keys[-1])
                
                for start in range(1, max_ep + 1, 5):
                    end = start + 4
                    batch_key = f"batch_{start}-{end}"
                    batch_list = []
                    
                    found = False
                    for i in range(start, end + 1):
                        k = str(i)
                        if k in episodes:
                            batch_list.append(episodes[k])
                            found = True
                    
                    if found:
                        batches[batch_key] = batch_list
        except:
            # If sorting fails, dump strict episodes to unmatched
            for k in episodes:
                unmatched.append(episodes[k])

    # 2. Process UNMATCHED (The "Catch-All" Batch)
    # If the regex failed for files, they land here.
    if unmatched:
        batches["batch_uncategorized"] = unmatched

    return batches

# ================= OTHER REGEX =================
TITLE_RE = re.compile(r"Title\s*:\s*(.+)", re.I)
SEASON_RE = re.compile(r"Season\s*:\s*(\d+)", re.I)
TOTAL_EP_RE = re.compile(r"Episode\s*:\s*(\d+)", re.I)
LANG_RE = re.compile(r"Language\s*:\s*(.+)", re.I)

# ================= GLOBAL STATE =================
UPDATE_RUNNING = False
UPDATE_PROGRESS = {
    "status": "idle",
    "current_channel": None,
    "processed": 0,
    "failed": 0
}

# ================= UTILS =================
def load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

def github_update_json(data):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    
    content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    encoded = base64.b64encode(content.encode()).decode()
    
    payload = {
        "message": "auto update anime index",
        "content": encoded,
        "branch": GITHUB_BRANCH
    }
    if sha: payload["sha"] = sha
    res = requests.put(url, headers=headers, json=payload)
    res.raise_for_status()

# ================= CHANNEL SCAN =================
async def scan_channel(client, channel_id, index, state):
    last_id = state.get(str(channel_id), 0)
    UPDATE_PROGRESS["current_channel"] = channel_id
    
    current_anime = None
    
    # Storage
    temp_episodes = {} # Good files: "1": {...}
    temp_specials = {} # Good specials
    temp_unmatched = [] # Files where regex FAILED
    
    parser = AnimeParser()

    print(f"Scanning {channel_id} starting after ID {last_id}...")

    async for msg in client.iter_messages(channel_id, min_id=last_id, reverse=True):
        text = msg.text or "" 
        
        # 1. START TAG
        if "</START>" in text:
            title_m = TITLE_RE.search(text)
            season_m = SEASON_RE.search(text)
            lang_m = LANG_RE.search(text)
            total_m = TOTAL_EP_RE.search(text)

            if title_m and season_m:
                current_anime = {
                    "title": title_m.group(1).strip(),
                    "season": season_m.group(1).strip(),
                    "language": lang_m.group(1).strip() if lang_m else "Unknown",
                    "total": int(total_m.group(1)) if total_m else 0
                }
                temp_episodes = {}
                temp_specials = {}
                temp_unmatched = []
                print(f"🔹 Started: {current_anime['title']} S{current_anime['season']}")
            
            state[str(channel_id)] = msg.id
            continue

        # 2. END TAG
        if "</End>" in text and current_anime:
            print(f"🔸 Ended: {current_anime['title']}")
            
            title = current_anime["title"]
            season = current_anime["season"]
            
            if title not in index: index[title] = {"seasons": {}}
            
            # --- SAFE BATCH GENERATION ---
            # If episodes found: create 1-5, 6-10
            # If NOT found: put in 'batch_uncategorized'
            final_batches = build_batches(temp_episodes, temp_unmatched)
            
            season_data = {
                "language": current_anime["language"],
                "total_episodes": current_anime["total"],
                "batches": final_batches,
                "specials": temp_specials
            }
            
            index[title]["seasons"][season] = season_data
            
            current_anime = None
            state[str(channel_id)] = msg.id
            continue

        # 3. EPISODES
        if current_anime and msg.file:
            file_name = msg.file.name or ""
            
            # Parse
            category, key = parser.parse(text, file_name)
            
            file_entry = {
                "file": msg.id, 
                "name": file_name
            }

            if category == 'episode':
                temp_episodes[key] = file_entry
                UPDATE_PROGRESS["processed"] += 1
            elif category == 'special':
                temp_specials[key] = file_entry
                UPDATE_PROGRESS["processed"] += 1
            else:
                # FAILED REGEX -> Add to unmatched list
                # This ensures the file is NOT LOST, just put in the "Catch-All" batch
                temp_unmatched.append(file_entry)
                UPDATE_PROGRESS["failed"] += 1
                # print(f"  -> Uncategorized: {file_name}")
            
    save_json(STATE_FILE, state)

# ================= MAIN BOT =================
async def main():
    global UPDATE_RUNNING

    index = load_json(JSON_FILE, {})
    state = load_json(STATE_FILE, {})

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    @client.on(events.NewMessage(pattern="/update"))
    async def update_handler(event):
        global UPDATE_RUNNING

        if event.sender_id not in ADMIN_IDS: return
        if UPDATE_RUNNING:
            await event.reply("⚠️ Update already running...")
            return

        UPDATE_RUNNING = True
        UPDATE_PROGRESS.update({"status": "starting", "processed": 0, "failed": 0})
        await event.reply("🔄 Scan started (Safe Mode: Batches + Fallback)...")

        try:
            for ch in CHANNELS:
                UPDATE_PROGRESS["status"] = "scanning"
                await scan_channel(client, ch, index, state)

            UPDATE_PROGRESS["status"] = "saving"
            save_json(JSON_FILE, index)
            
            if GITHUB_TOKEN:
                UPDATE_PROGRESS["status"] = "uploading"
                github_update_json(index)
                await event.reply("✅ Update Completed & Uploaded to GitHub!")
            else:
                await event.reply("✅ Update Completed (Local Only)")

        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
            print(f"ERROR: {e}")
        
        finally:
            UPDATE_RUNNING = False

    @client.on(events.NewMessage(pattern="/status"))
    async def status_handler(event):
        if event.sender_id not in ADMIN_IDS: return
        msg = (
            f"📊 **Status:** {UPDATE_PROGRESS['status']}\n"
            f"📺 **Channel:** {UPDATE_PROGRESS['current_channel']}\n"
            f"✅ **Processed:** {UPDATE_PROGRESS['processed']}\n"
            f"⚠️ **Uncategorized:** {UPDATE_PROGRESS['failed']}"
        )
        await event.reply(msg)

    print("🤖 Bot is active...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())