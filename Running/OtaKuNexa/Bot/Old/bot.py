import re
import json
import asyncio
import os
import base64
import requests
from telethon import TelegramClient, events
from collections import defaultdict

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
GITHUB_TOKEN = "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" 
GITHUB_OWNER = "ayarsbusiness-bot"
GITHUB_REPO = "anime-index"
GITHUB_BRANCH = "main"
GITHUB_FILE = "anime_index.json"

# ================= 1. ENHANCED SMART PARSER =================
class AnimeParser:
    def __init__(self):
        # Noise patterns to remove
        self.noise_patterns = [
            r'\[[^\]]*\]', r'\([^)]*\)',                    # Brackets
            r'\b(?:1080p|720p|480p|2160p|4k)\b',           # Resolutions
            r'\b(?:x264|x265|HEVC|AVC|h\.264|h\.265)\b',   # Codecs
            r'\b(?:10bit|Hi10|AAC|FLAC|DDP5\.1|Opus)\b',   # Audio
            r'@\w+', r'www\.\w+\.\w+',                     # Watermarks
            r'\b(?:19|20)\d{2}\b',                         # Years
            r'\.(?:mp4|mkv|avi|webm|mov|flv|wmv)\b',       # Extensions
            r'\b(?:Sub|Dub|Eng|Hindi|Multi)\b',            # Language tags
            r'\b(?:BD|BluRay|WEB-DL|HDTV|CAM)\b',          # Source
            r'\b(?:Complete|Batch|End|Final)\b',           # Status
            r'[^\w\s\-\.]',                                # Special chars except hyphen/dot
        ]
        
        # Episode number patterns (ordered by priority)
        self.episode_patterns = [
            # Pattern 1: Ep 23, Ep.23, Episode 23
            r'\b(?:Ep(?:isode)?[\.\s]*)(\d{1,4})\b',
            
            # Pattern 2: E23, E-23, E_23
            r'\bE[-_]?(\d{1,4})\b',
            
            # Pattern 3: [23], (23), -23-
            r'[\[\(\-]\s*(\d{1,4})\s*[\]\)\-]',
            
            # Pattern 4: Number at start with separator
            r'^\s*(\d{1,4})[-_\s]+',
            
            # Pattern 5: Number at end with separator
            r'[-_\s]+(\d{1,4})\s*$',
            
            # Pattern 6: Standalone 2-4 digit numbers
            r'\b(\d{2,4})\b',
        ]
        
        # Special patterns
        self.special_patterns = [
            r'\b(?:OVA|OAD)[-\s]*(\d+)?\b',
            r'\b(?:Special|SP)[-\s]*(\d+)?\b',
            r'\bMovie\b',
            r'\b(?:NCED|NCOP)\b',
            r'\bPV\b',
        ]
        
        # Season detection in files
        self.season_in_file = [
            r'\bS(\d+)\b',
            r'\bSeason\s*(\d+)\b',
            r'[-_\s](\d+)of\d+',  # 1of12 pattern
        ]

    def clean_text(self, text):
        """Remove noise from text while preserving episode numbers"""
        if not text:
            return ""
        
        # First pass: remove obvious noise
        cleaned = str(text)
        for pattern in self.noise_patterns:
            cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
        
        # Remove extra spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

    def extract_season_from_caption(self, caption, current_season):
        """Extract season number from caption if present"""
        if not caption:
            return current_season
            
        season_patterns = [
            r'\bS(\d+)\b',
            r'\bSeason\s*(\d+)\b',
            r'[-_\s]S?(\d+)E\d+',  # S01E01 pattern
        ]
        
        for pattern in season_patterns:
            match = re.search(pattern, caption, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except:
                    pass
        
        return current_season

    def extract_episode_number(self, text):
        """Extract episode number with priority to more specific patterns"""
        if not text:
            return None
        
        cleaned = self.clean_text(text)
        
        # Try each pattern in priority order
        for pattern in self.episode_patterns:
            matches = re.findall(pattern, cleaned)
            if matches:
                for match in matches:
                    try:
                        num = int(match)
                        # Sanity check: episode numbers usually 1-2000
                        if 1 <= num <= 2000:
                            return str(num)
                    except:
                        continue
        
        return None

    def parse(self, caption, file_name, current_season=None):
        """
        Parse episode/special information from caption and filename
        Returns: (category, key, detected_season)
        """
        # Check for specials first
        for source in [caption, file_name]:
            if not source:
                continue
                
            for pattern in self.special_patterns:
                match = re.search(pattern, source, re.IGNORECASE)
                if match:
                    num = match.group(1) if match.group(1) else "1"
                    prefix = "OVA" if "ova" in source.lower() else "Special"
                    if "movie" in source.lower():
                        return 'special', "Movie", current_season
                    return 'special', f"{prefix}_{num}", current_season
        
        # Extract episode number with priority:
        # 1. From caption (with season detection)
        # 2. From filename
        
        detected_season = self.extract_season_from_caption(caption, current_season)
        
        # Try caption first
        ep_num = self.extract_episode_number(caption)
        if ep_num:
            return 'episode', ep_num, detected_season
            
        # Try filename
        ep_num = self.extract_episode_number(file_name)
        if ep_num:
            return 'episode', ep_num, detected_season
        
        return 'batch', None, detected_season

# ================= 2. IMPROVED BATCHING SYSTEM =================
def build_smart_batches(episodes_dict):
    """
    Create perfect batches of 5 episodes maintaining order
    Handles gaps in episode numbering intelligently
    """
    if not episodes_dict:
        return {}
    
    try:
        # Convert keys to integers and sort
        episode_nums = []
        for k in episodes_dict.keys():
            try:
                episode_nums.append(int(k))
            except:
                continue
        
        if not episode_nums:
            return {"batch_uncategorized": list(episodes_dict.values())}
        
        episode_nums.sort()
        batches = {}
        
        # Group into batches of 5
        current_batch = 1
        current_batch_eps = []
        
        for ep_num in episode_nums:
            ep_str = str(ep_num)
            if ep_str in episodes_dict:
                current_batch_eps.append(episodes_dict[ep_str])
                
                # When we have 5 episodes or reach a gap
                if len(current_batch_eps) == 5:
                    batches[f"batch{current_batch}"] = current_batch_eps.copy()
                    current_batch += 1
                    current_batch_eps = []
        
        # Add remaining episodes
        if current_batch_eps:
            batches[f"batch{current_batch}"] = current_batch_eps
        
        return batches
        
    except Exception as e:
        print(f"Batch building error: {e}")
        return {"batch_uncategorized": list(episodes_dict.values())}

def group_unmatched_files(unmatched_files, anime_meta, parser):
    """
    Try to intelligently group unmatched files
    """
    if not unmatched_files:
        return []
    
    # Try to extract episode numbers from unmatched files
    matched_eps = {}
    remaining_unmatched = []
    
    for file_info in unmatched_files:
        file_name = file_info.get("name", "")
        caption = file_info.get("caption", "")
        
        ep_num = parser.extract_episode_number(caption) or parser.extract_episode_number(file_name)
        
        if ep_num:
            matched_eps[ep_num] = file_info
        else:
            remaining_unmatched.append(file_info)
    
    # If we found episodes in unmatched, create batches
    if matched_eps:
        batches = build_smart_batches(matched_eps)
        return [{"type": "batch_group", "data": batches}] + remaining_unmatched
    
    return remaining_unmatched

# ================= 3. ENHANCED REGEX FOR START TAG =================
TITLE_RE = re.compile(r"Title\s*[:=]?\s*(.+?)(?:\n|$)", re.I)
SEASON_RE = re.compile(r"Season\s*[:=]?\s*(\d+)", re.I)
TOTAL_EP_RE = re.compile(r"(?:Episode|Episodes)\s*[:=]?\s*(\d+)", re.I)
LANG_RE = re.compile(r"Language\s*[:=]?\s*(.+?)(?:\n|$)", re.I)
MAL_ID_RE = re.compile(r"MAL(?:[-_]?ID)?\s*[:=]?\s*(.+?)(?:\n|$)", re.I)
START_TAG_RE = re.compile(r"<START>([\s\S]*?)</START>", re.I)

def parse_start_tag(text):
    """Extract metadata from START tag with flexible parsing"""
    match = START_TAG_RE.search(text)
    if not match:
        return None
    
    content = match.group(1)
    
    # Try to extract each field
    title_match = TITLE_RE.search(content)
    season_match = SEASON_RE.search(content)
    lang_match = LANG_RE.search(content)
    total_match = TOTAL_EP_RE.search(content)
    mal_match = MAL_ID_RE.search(content)
    
    if not title_match or not season_match:
        return None
    
    # Parse MAL IDs (comma separated)
    mal_ids = []
    if mal_match:
        mal_text = mal_match.group(1).strip()
        # Split by comma or space
        ids = re.split(r'[,\s]+', mal_text)
        mal_ids = [id.strip() for id in ids if id.strip()]
    
    return {
        "title": title_match.group(1).strip(),
        "season": season_match.group(1).strip(),
        "language": lang_match.group(1).strip() if lang_match else "Unknown",
        "total": int(total_match.group(1)) if total_match else 0,
        "mal_ids": mal_ids
    }

# ================= 4. SAVE LOGIC WITH BETTER VALIDATION =================
def save_anime_to_index(anime_meta, episodes, specials, unmatched, index, parser):
    if not anime_meta:
        return
    
    title = anime_meta["title"]
    season = anime_meta["season"]
    lang = anime_meta["language"]
    
    print(f"💾 Processing: {title} S{season} [{lang}] - Episodes: {len(episodes)}, Specials: {len(specials)}, Unmatched: {len(unmatched)}")
    
    # Initialize structure
    if title not in index:
        index[title] = {"seasons": {}}
    
    if season not in index[title]["seasons"]:
        index[title]["seasons"][season] = {
            "total_episodes": anime_meta["total"],
            "mal_ids": anime_meta.get("mal_ids", []),
            "languages": {}
        }
    
    season_node = index[title]["seasons"][season]
    
    # Merge MAL IDs
    existing_ids = set(str(x) for x in season_node.get("mal_ids", []))
    incoming_ids = set(str(x) for x in anime_meta.get("mal_ids", []))
    season_node["mal_ids"] = sorted(list(existing_ids.union(incoming_ids)))
    
    # Process unmatched files
    processed_unmatched = group_unmatched_files(unmatched, anime_meta, parser)
    
    # Build perfect batches
    final_batches = build_smart_batches(episodes)
    
    # Add any processed unmatched batches
    for item in processed_unmatched:
        if isinstance(item, dict) and item.get("type") == "batch_group":
            final_batches.update(item["data"])
    
    # Save to index
    if "languages" not in season_node:
        season_node["languages"] = {}
    
    season_node["languages"][lang] = {
        "batches": final_batches,
        "specials": specials,
        "unmatched": [f for f in processed_unmatched if not isinstance(f, dict) or f.get("type") != "batch_group"]
    }

# ================= 5. ENHANCED SCANNER =================
async def scan_channel(client, channel_id, index, state, force_rescan=False):
    last_id = 0 if force_rescan else state.get(str(channel_id), 0)
    current_anime = None
    temp_ep = {}
    temp_sp = {}
    temp_un = []
    parser = AnimeParser()
    
    print(f"🚀 Scanning channel {channel_id} from message {last_id}")
    
    async for msg in client.iter_messages(channel_id, min_id=last_id, reverse=True):
        text = msg.text or ""
        
        # --- START TAG DETECTION ---
        if "</START>" in text.upper():
            if current_anime:
                save_anime_to_index(current_anime, temp_ep, temp_sp, temp_un, index, parser)
            
            anime_meta = parse_start_tag(text)
            if anime_meta:
                current_anime = anime_meta
                temp_ep, temp_sp, temp_un = {}, {}, []
                print(f"📁 Starting: {anime_meta['title']} S{anime_meta['season']}")
            else:
                print(f"⚠️ Invalid START tag in message {msg.id}")
            
            state[str(channel_id)] = msg.id
            continue
        
        # --- END TAG DETECTION ---
        if "</END>" in text.upper():
            if current_anime:
                save_anime_to_index(current_anime, temp_ep, temp_sp, temp_un, index, parser)
                print(f"✅ Finished: {current_anime['title']} S{current_anime['season']}")
                current_anime = None
            
            state[str(channel_id)] = msg.id
            continue
        
        # --- FILE PROCESSING (only if we have active anime) ---
        if current_anime and msg.file:
            file_name = msg.file.name or ""
            
            # Parse with current season context
            cat, key, detected_season = parser.parse(
                text, 
                file_name, 
                current_anime["season"]
            )
            
            # If season detected in file differs from current, log warning
            if detected_season and str(detected_season) != current_anime["season"]:
                print(f"⚠️ Season mismatch: Expected S{current_anime['season']}, found S{detected_season} in file")
            
            entry = {
                "file": msg.id,
                "name": file_name,
                "caption": text[:200] if text else ""  # Store first 200 chars of caption
            }
            
            if cat == 'episode' and key:
                temp_ep[key] = entry
                UPDATE_PROGRESS["processed"] += 1
            elif cat == 'special' and key:
                temp_sp[key] = entry
                UPDATE_PROGRESS["processed"] += 1
            else:
                temp_un.append(entry)
            
            state[str(channel_id)] = msg.id
    
    # Save any remaining anime
    if current_anime:
        save_anime_to_index(current_anime, temp_ep, temp_sp, temp_un, index, parser)
    
    save_json(STATE_FILE, state)
    return index

# ================= UTILITY FUNCTIONS =================
UPDATE_PROGRESS = {"status": "idle", "processed": 0}

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return default

def save_json(path, data):
    # Simple sort function
    def sort_dict(d):
        if isinstance(d, dict):
            return {k: sort_dict(v) for k, v in sorted(d.items())}
        elif isinstance(d, list):
            return [sort_dict(item) for item in d]
        else:
            return d
    
    sorted_data = sort_dict(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved {len(data)} anime to {path}")

def github_update_json(data):
    if not GITHUB_TOKEN or "YOUR_GITHUB" in GITHUB_TOKEN:
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        
        # Get current SHA
        r = requests.get(url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None
        
        # Sort and encode data
        def sort_dict(d):
            if isinstance(d, dict):
                return {k: sort_dict(v) for k, v in sorted(d.items())}
            elif isinstance(d, list):
                return [sort_dict(item) for item in d]
            else:
                return d
        
        sorted_data = sort_dict(data)
        content = json.dumps(sorted_data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode()).decode()
        
        # Create payload
        payload = {
            "message": f"Auto update: {len(data)} anime",
            "content": encoded,
            "branch": GITHUB_BRANCH
        }
        if sha:
            payload["sha"] = sha
        
        # Update
        response = requests.put(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print("✅ Successfully updated GitHub")
        else:
            print(f"❌ GitHub update failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ GitHub error: {e}")

# ================= MAIN FUNCTION =================
async def main():
    # Load existing data
    index = load_json(JSON_FILE, {})
    state = load_json(STATE_FILE, {})
    
    print(f"📊 Loaded {len(index)} anime from {JSON_FILE}")
    
    # Initialize client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    
    print(f"✅ Logged in as {await client.get_me()}")
    
    # Update handler
    @client.on(events.NewMessage(pattern=r"/update(?:\s+(force))?"))
    async def update_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        
        force = (event.pattern_match.group(1) == "force")
        await event.reply("🔍 Starting scan..." + (" (force rescan)" if force else ""))
        
        UPDATE_PROGRESS["status"] = "scanning"
        UPDATE_PROGRESS["processed"] = 0
        
        try:
            for i, channel_id in enumerate(CHANNELS):
                await event.reply(f"📡 Scanning channel {i+1}/{len(CHANNELS)}...")
                await scan_channel(client, channel_id, index, state, force_rescan=force)
            
            # Save results
            save_json(JSON_FILE, index)
            github_update_json(index)
            
            await event.reply(
                f"✅ Scan complete!\n"
                f"• Total anime: {len(index)}\n"
                f"• Files processed: {UPDATE_PROGRESS['processed']}\n"
                f"• Saved to {JSON_FILE}"
            )
            
        except Exception as e:
            await event.reply(f"❌ Error during scan: {str(e)}")
            print(f"Scan error: {e}")
        finally:
            UPDATE_PROGRESS["status"] = "idle"
    
    # Status command
    @client.on(events.NewMessage(pattern="/status"))
    async def status_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        
        status = f"""
🤖 **Anime Indexer Status**
• Indexed Anime: {len(index)}
• Status: {UPDATE_PROGRESS['status']}
• Last Processed: {UPDATE_PROGRESS['processed']}
• Channels: {len(CHANNELS)}
        """
        await event.reply(status)
    
    print("🤖 Bot is running. Commands:")
    print("• /update - Scan for new files")
    print("• /update force - Force rescan all")
    print("• /status - Show current status")
    
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())