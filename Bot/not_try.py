import re
import json
import asyncio
import os
import time
import requests
import base64
from groq import Groq
from telethon import TelegramClient, events
from difflib import SequenceMatcher

# ================= CONFIGURATION =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
SESSION_NAME = "anime_indexer"

# 🔴 PASTE YOUR GROQ KEY HERE
GROQ_API_KEY = "gsk_..." 

CHANNELS = [-1003175788400, -1003498912074]
ADMIN_IDS = [8466952185] 

MODEL_NAME = "llama-3.3-70b-versatile" 
AUDIT_DIR = "ai_audit_logs"

# ================= SETUP =================
if not os.path.exists(AUDIT_DIR):
    os.makedirs(AUDIT_DIR)

AI_AVAILABLE = False
client = None

def configure_ai():
    global AI_AVAILABLE, client
    if not GROQ_API_KEY:
        AI_AVAILABLE = False
        return
    try:
        client = Groq(api_key=GROQ_API_KEY)
        AI_AVAILABLE = True
        print(f"✅ Groq AI Initialized")
    except Exception as e:
        print(f"❌ Groq Init Error: {e}")
        AI_AVAILABLE = False

configure_ai()

# ================= FILES & DATA =================
JSON_FILE = "anime_index.json"
SUMMARY_FILE = "available_animes.json"
STATE_FILE = "scan_state.json"
GITHUB_TOKEN = "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" 
GITHUB_OWNER = "ayarsbusiness-bot"
GITHUB_REPO = "anime-index"
GITHUB_BRANCH = "main"
GITHUB_FILE = "anime_index.json"

# ================= 1. SECURITY FILTER (Anti-Bleed) =================
def is_valid_file_for_anime(filename, caption, anime_title):
    """
    Ensures file actually belongs to the current anime block.
    """
    # 1. Prepare strings
    clean_name = filename.lower().replace("_", " ").replace(".", " ").replace("-", " ")
    clean_title = anime_title.lower().replace(":", "").replace("-", " ")
    
    # 2. Direct Match
    if clean_title in clean_name: return True
        
    # 3. Generic Check (e.g. "10.mkv", "S01E02", "Episode 05") 
    # If the file is generic, we assume it belongs to the active block.
    name_core = re.sub(r'\[.*?\]|\(.*?\)|@\w+', '', clean_name).strip()
    if len(name_core) < 30 and re.search(r'\d', name_core):
        return True 

    # 4. Fuzzy Match Rejection
    # If the filename has a distinct title that DOES NOT match the current block
    ratio = SequenceMatcher(None, clean_title, clean_name).ratio()
    if ratio < 0.2: return False # Likely a bleed-over from another anime
        
    return True 

# ================= 2. ULTRA REGEX ENGINE (Customized for your Dump) =================
class RegexEngine:
    @staticmethod
    def extract_episode(text):
        """
        Extracts episode numbers using patterns found in your channel dump.
        """
        if not text: return None
        
        # Clean text: remove newlines and common junk
        clean = text.replace("\n", " ").strip()
        # Remove [720p], (Hevc), @ChannelName to avoid confusion
        clean = re.sub(r'\[.*?\]|\(.*?\)|@\w+', '', clean).strip()
        
        # --- CAPTION PATTERNS (Priority) ---
        
        # P1: "Season 2 Episode - 01" (Haikyuu S2 style)
        m = re.search(r"Episode\s*-\s*(\d+)", clean, re.IGNORECASE)
        if m: return float(m.group(1)), float(m.group(1))

        # P2: "• Episode: 1" (Lookism style)
        m = re.search(r"•\s*Episode:?\s*(\d+)", clean, re.IGNORECASE)
        if m: return float(m.group(1)), float(m.group(1))

        # P3: "Episode 05" or "Ep 05"
        m = re.search(r"(?:Episode|Ep)\.?\s*(\d+)(?:-?(\d+))?", clean, re.IGNORECASE)
        if m: return float(m.group(1)), float(m.group(2)) if m.group(2) else float(m.group(1))

        # --- FILENAME PATTERNS ---

        # P4: "[S1-01]" (Genocyber style)
        m = re.search(r"\[S\d+-(\d+)\]", clean, re.IGNORECASE)
        if m: return float(m.group(1)), float(m.group(1))

        # P5: "S01E05" (Standard)
        m = re.search(r"S\d+E(\d+)(?:-E?(\d+))?", clean, re.IGNORECASE)
        if m: return float(m.group(1)), float(m.group(2)) if m.group(2) else float(m.group(1))

        # P6: " - 05 " (Death Note style: "Death Note S1 - 01")
        # Looks for hyphen surrounded by spaces/brackets/dots
        m = re.search(r"\s-\s(\d{1,3})(?:\s|\[|\.|$)", clean)
        if m: return float(m.group(1)), float(m.group(1))
        
        # P7: "10.mkv" (Generic Number Start)
        # Matches start of string or space, followed by number, then extension
        m = re.search(r'(?:^|\s)(\d{1,3})\.(?:mkv|mp4)', text, re.IGNORECASE)
        if m: return float(m.group(1)), float(m.group(1))

        return None

# ================= 3. HYBRID HANDLER (No-Chunk AI) =================
class HybridHandler:
    def process_season(self, files, meta):
        final_mapping = {}
        files_for_ai = []

        print(f"🔍 Hybrid Scan: {len(files)} files for {meta['title']}...")

        # STEP 1: Local Regex (Caption Priority)
        for file in files:
            # Security Check
            if not is_valid_file_for_anime(file['name'], file['caption'], meta['title']):
                continue 

            found_ep = None
            
            # A. Check Caption First (Highest Trust)
            if file['caption']:
                found_ep = RegexEngine.extract_episode(file['caption'])
            
            # B. Check Name Second (If caption didn't give a number)
            if not found_ep and file['name']:
                found_ep = RegexEngine.extract_episode(file['name'])
                
            if found_ep:
                start, end = found_ep
                final_mapping[file['file_id']] = {
                    "id": f"ID_{file['file_id']}",
                    "type": "episode",
                    "num": start,
                    "end_num": end
                }
            else:
                # Regex failed? Add to AI pile.
                files_for_ai.append(file)

        # STEP 2: AI Clean Up (Global Context)
        if files_for_ai and AI_AVAILABLE:
            print(f"⚠️ Regex missed {len(files_for_ai)} files. Sending ALL to AI for context...")
            
            # 🔴 WE SEND ALL FILES (Correct Context)
            # We send the ones Regex solved (for context) + the ones it missed
            ai_results = self._process_with_groq(files, meta)
            
            # Update mapping with AI results (AI overwrites only if it finds something valid)
            for fid, result in ai_results.items():
                # Only accept AI result if we didn't find it via regex, OR if regex was unsure
                if fid not in final_mapping or (fid in files_for_ai): 
                    final_mapping[fid] = result
        
        return final_mapping

    def _process_with_groq(self, files, meta):
        files_text = ""
        for file in files:
            clean_name = file['name']
            clean_caption = file['caption'].replace('\n', ' ')[:300]
            files_text += f"ID_{file['file_id']}: Caption='{clean_caption}' Name='{clean_name}'\n"

        prompt = f"""
        You are an Anime Indexing Bot. 
        Target: "{meta['title']}" (Season {meta['season']})

        Task: Extract Episode Numbers from the list below.
        
        RULES:
        1. **Caption is King:** Trust the Caption text over the filename.
        2. **Garbage Files:** If the file looks like "GDToT" or random chars, ONLY use the Caption.
        3. **Multi-Episode:** If "01-02", return "num": 1, "end_num": 2.
        4. **Specials:** If "OVA", "Special", "Movie" -> return "type": "ignore".
        5. **Ignore:** Trailers, Openings, or unrelated files -> "type": "ignore".

        DATA:
        {files_text}

        OUTPUT JSON:
        {{ "files": [ 
            {{ "id": "ID_...", "type": "episode", "num": 1 }},
            {{ "id": "ID_...", "type": "episode", "num": 1, "end_num": 2 }}
        ] }}
        """
        
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "JSON only."},
                    {"role": "user", "content": prompt}
                ],
                model=MODEL_NAME, temperature=0.1, response_format={"type": "json_object"}
            )
            response = json.loads(chat_completion.choices[0].message.content)
            
            mapping = {}
            items = response if isinstance(response, list) else response.get("files", [])
            for item in items:
                try:
                    msg_id = int(str(item["id"]).replace("ID_", ""))
                    mapping[msg_id] = item
                except: continue
            return mapping

        except Exception as e:
            print(f"❌ AI Error: {e}")
            return {}

# ================= 4. BATCHING & SORTING =================
def build_batches(episodes_list, specials_list, unmatched):
    batches = {}
    valid_eps = []
    covered_numbers = set()

    # 1. Process List
    for data in episodes_list:
        try:
            start_num = float(data['num'])
            end_num = float(data.get('end_num', start_num))

            curr = int(start_num)
            while curr <= int(end_num):
                covered_numbers.add(curr)
                curr += 1
            
            clean_data = {k:v for k,v in data.items() if k not in ['num', 'end_num', 'type']}
            valid_eps.append((start_num, clean_data))
        except: 
            unmatched.append(data)

    # 2. Sort by Episode Number
    valid_eps.sort(key=lambda x: x[0])

    # 3. Create Batches (Size 5)
    if valid_eps:
        buckets = {}
        for ep_num, file_data in valid_eps:
            b_idx = (int(ep_num) - 1) // 5
            if b_idx not in buckets: buckets[b_idx] = []
            buckets[b_idx].append(file_data)
            
        for idx in sorted(buckets.keys()):
            # Natural Sort inside batch (Fixes 10.mkv vs 9.mkv sorting)
            sorted_batch = sorted(buckets[idx], key=lambda x: natural_sort_key(x['name']))
            batches[f"batch{idx + 1}"] = sorted_batch

    # 4. Missing Eps
    missing_list = []
    if valid_eps:
        max_ep = int(max([x[0] for x in valid_eps] + list(covered_numbers)))
        full_range = set(range(1, max_ep + 1))
        missing_list = sorted(list(full_range - covered_numbers))

    # 5. Uncategorized
    if unmatched: batches["batch_uncategorized"] = unmatched

    return batches, missing_list, {}

# ================= UTILS & TELEGRAM =================
def natural_sort_key(key):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(key))]

def sort_dict_recursively(data):
    if isinstance(data, dict):
        sorted_items = sorted(data.items(), key=lambda item: natural_sort_key(item[0]))
        return {k: sort_dict_recursively(v) for k, v in sorted_items}
    elif isinstance(data, list): return data
    else: return data

TITLE_RE = re.compile(r"Title\s*:\s*(.+)", re.I)
SEASON_RE = re.compile(r"Season\s*:\s*(\d+)", re.I)
TOTAL_EP_RE = re.compile(r"Episode\s*:\s*(\d+)", re.I)
LANG_RE = re.compile(r"Language\s*:\s*(.+)", re.I)
MAL_ID_RE = re.compile(r"mal_id\s*:\s*(.+)", re.I)

UPDATE_PROGRESS = {"processed": 0}

def load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(path, data):
    sorted_data = sort_dict_recursively(data)
    with open(path, "w", encoding="utf-8") as f: json.dump(sorted_data, f, indent=2, ensure_ascii=False)

def github_update_file(filename, content_data):
    if not GITHUB_TOKEN or "YOUR_GITHUB" in GITHUB_TOKEN: return
    try:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{filename}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None
        
        sorted_data = sort_dict_recursively(content_data) if isinstance(content_data, dict) else content_data
        content = json.dumps(sorted_data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode()).decode()
        
        payload = {"message": f"update {filename}", "content": encoded, "branch": GITHUB_BRANCH}
        if sha: payload["sha"] = sha
        requests.put(url, headers=headers, json=payload)
    except Exception as e: print(f"GitHub Error: {e}")

# ================= SAVE & SCAN =================
def find_title_by_mal_id(index, mal_ids_to_check, season_num):
    if not mal_ids_to_check: return None
    target_ids = set(str(x) for x in mal_ids_to_check)
    for title, data in index.items():
        if "seasons" not in data: continue
        if season_num in data["seasons"]:
            season_data = data["seasons"][season_num]
            existing_ids = set(str(x) for x in season_data.get("mal_ids", []))
            if not target_ids.isdisjoint(existing_ids): return title
    return None

def save_anime_to_index(anime_meta, episodes, specials, unmatched, index, missing_eps):
    existing_title = find_title_by_mal_id(index, anime_meta["mal_ids"], anime_meta["season"])
    title = existing_title if existing_title else anime_meta["title"]
    season = anime_meta["season"]
    lang = anime_meta["language"] or "Unknown"

    print(f"💾 Saving: {title} S{season} [{lang}]")

    if title not in index: index[title] = {"seasons": {}}
    if season not in index[title]["seasons"]:
        index[title]["seasons"][season] = {
            "total_episodes": anime_meta["total"], "mal_ids": [], "languages": {}, "missing_episodes": []
        }
    
    season_node = index[title]["seasons"][season]
    season_node["missing_episodes"] = missing_eps

    existing_ids = set(str(x) for x in season_node.get("mal_ids", []))
    incoming_ids = set(str(x) for x in anime_meta.get("mal_ids", []))
    if incoming_ids:
        season_node["mal_ids"] = sorted(list(existing_ids.union(incoming_ids)))

    if "languages" not in season_node: season_node["languages"] = {}
    season_node["languages"][lang] = {"batches": episodes, "specials": specials}

async def process_season_block(meta, collected_files, index, handler):
    if not meta or not collected_files: return
    
    mapping_results = handler.process_season(collected_files, meta)
    
    ep_list_raw = []
    sp_list_raw = []
    un_list = []

    for file_obj in collected_files:
        msg_id = file_obj['file_id']
        entry = {
            "file": msg_id, 
            "channel_id": file_obj['channel_id'],
            "name": file_obj['name']
        }
        
        if msg_id in mapping_results:
            result = mapping_results[msg_id]
            if result['type'] == 'episode':
                entry['num'] = result['num']
                entry['end_num'] = result.get('end_num', result['num'])
                ep_list_raw.append(entry)
            elif result['type'] == 'special':
                pass # Ignored as per rules
            else:
                pass 
        else:
            # Re-check security before adding to Uncategorized
            if is_valid_file_for_anime(file_obj['name'], file_obj['caption'], meta['title']):
                un_list.append(entry)

    final_batches, missing_eps, final_specials = build_batches(ep_list_raw, sp_list_raw, un_list)
    UPDATE_PROGRESS["processed"] += len(collected_files)
    save_anime_to_index(meta, final_batches, final_specials, un_list, index, missing_eps)

async def scan_channel(client, channel_id, index, state, force_rescan=False):
    last_id = 0 if force_rescan else state.get(str(channel_id), 0)
    curr_meta = None
    curr_files = []
    handler = HybridHandler()
    print(f"🚀 Scanning {channel_id} from {last_id}")

    async for msg in client.iter_messages(channel_id, min_id=last_id, reverse=True):
        text = msg.text or ""
        if "</START>" in text:
            if curr_meta: await process_season_block(curr_meta, curr_files, index, handler)
            tm = TITLE_RE.search(text)
            sm = SEASON_RE.search(text)
            lm = LANG_RE.search(text)
            total_m = TOTAL_EP_RE.search(text)
            mal_m = MAL_ID_RE.search(text)
            if tm and sm:
                mal_ids = [x.strip() for x in mal_m.group(1).split(',')] if mal_m else []
                curr_meta = {
                    "title": tm.group(1).strip(), "season": sm.group(1).strip(),
                    "language": lm.group(1).strip() if lm else "Unknown",
                    "total": int(total_m.group(1)) if total_m else 0, "mal_ids": mal_ids
                }
                curr_files = [] 
            state[str(channel_id)] = msg.id
            continue

        if curr_meta and msg.file:
            curr_files.append({
                "file_id": msg.id, "channel_id": channel_id,
                "name": msg.file.name or "Unknown", "caption": text or "" 
            })
            state[str(channel_id)] = msg.id

    if curr_meta: await process_season_block(curr_meta, curr_files, index, handler)
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
        await event.reply("☢️ Hybrid Indexer Starting..." if force else "🔄 Updating...")
        UPDATE_PROGRESS["processed"] = 0
        try:
            for ch in CHANNELS: await scan_channel(client, ch, index, state, force_rescan=force)
            save_json(JSON_FILE, index)
            github_update_file(GITHUB_FILE, index)
            summary = generate_availability_summary(index)
            github_update_file(SUMMARY_FILE, summary)
            await event.reply(f"✅ Done! Processed: {UPDATE_PROGRESS['processed']}")
        except Exception as e:
            await event.reply(f"❌ Error: {e}")
            import traceback; traceback.print_exc()
            
    print("🤖 Hybrid Bot Active.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())