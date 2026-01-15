import re
import json
import asyncio
import os
import time
import requests
import base64 # Added for GitHub update
from groq import Groq  # pip install groq
from telethon import TelegramClient, events

# ================= CONFIGURATION =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
SESSION_NAME = "anime_indexer"

# 🔴 PASTE YOUR GROQ KEY HERE (Starts with gsk_...)
GROQ_API_KEY = "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" 

CHANNELS = [-1003175788400, -1003498912074]
ADMIN_IDS = [8466952185] 

# Using the smart model for accuracy
MODEL_NAME = "llama-3.3-70b-versatile" 

# Confidence Threshold (Not strictly needed for Groq but kept for compatibility)
CONFIDENCE_THRESHOLD = 0.6 
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
STATE_FILE = "scan_state.json"
GITHUB_TOKEN = "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" 
GITHUB_OWNER = "ayarsbusiness-bot"
GITHUB_REPO = "anime-index"
GITHUB_BRANCH = "main"
GITHUB_FILE = "anime_index.json"

# ================= 1. GROQ AI HANDLER =================
class BulkAIHandler:
    def process_season(self, files, meta):
        if not AI_AVAILABLE or not files: return {}

        season_num = meta["season"]
        title = meta["title"]
        
        files.sort(key=lambda x: x['name'])
        
        prompt = self._build_prompt(files, title, season_num)
        raw_response = self._call_groq(prompt)
        
        self._save_audit_log(title, season_num, files, raw_response)
        
        final_mapping = {}
        if raw_response:
            # Groq might return the dict directly or wrapped in "files"
            items = raw_response if isinstance(raw_response, list) else raw_response.get("files", [])
            
            for item in items:
                try:
                    # Confidence check (optional for Groq, but good practice)
                    confidence = item.get("confidence", 1.0) # Default to 1.0 if missing
                    if confidence < CONFIDENCE_THRESHOLD:
                         continue 
                    
                    msg_id = int(item["id"].replace("ID_", ""))
                    final_mapping[msg_id] = item
                except: continue
                
        return final_mapping

    def _save_audit_log(self, title, season, files, response):
        clean_title = re.sub(r'[\\/*?:"<>|]', "", title)
        filename = f"{AUDIT_DIR}/{clean_title}_S{season}_{int(time.time())}.json"
        log_data = {
            "anime": title, "season": season, "files_count": len(files),
            "ai_response": response, "input_sample": [f['name'] for f in files[:5]]
        }
        try:
            with open(filename, "w", encoding="utf-8") as f: json.dump(log_data, f, indent=2)
        except: pass

    def _build_prompt(self, files, title, season):
        files_text = ""
        for file in files:
            clean_name = file['name']
            files_text += f"ID_{file['file_id']}: {clean_name}\n"

        return f"""
        You are an Anime Indexing Bot.
        Target Anime: "{title}"
        Target Season: {season}

        Task: Analyze the filenames and extract Episode Numbers.

        DATA:
        {files_text}

        RULES:
        1. **Strict Matching**: Only match files for "{title}". 
           - If file is for DIFFERENT anime, type="ignore".
           - If season doesn't match, type="ignore".
        2. **Structure**: 
           - Episode: "type": "episode", "num": 1
           - Special: "type": "special", "name": "OVA 1"
           - Ignore: "type": "ignore"
        3. **Format**: Return ONLY valid JSON.
        
        OUTPUT JSON:
        {{ "files": [
            {{"id": "ID_123", "type": "episode", "num": 1}},
            {{"id": "ID_456", "type": "special", "name": "OVA 1"}}
        ] }}
        """

    def _call_groq(self, prompt):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a JSON-only API. Output strict JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    model=MODEL_NAME,
                    temperature=0.1, 
                    response_format={"type": "json_object"}
                )
                response_text = chat_completion.choices[0].message.content
                return json.loads(response_text)
            except Exception as e:
                print(f"⚠️ Groq Error (Attempt {attempt+1}): {e}")
                time.sleep(5) 
        return {}

# ================= 2. BATCHING (EXACT ORIGINAL LOGIC) =================
def build_batches(episodes, unmatched):
    batches = {}
    valid_eps = []
    
    for num_str, data in episodes.items():
        try: valid_eps.append((float(num_str), data)) # Changed to float to support 6.5
        except: unmatched.append(data)
    
    valid_eps.sort(key=lambda x: x[0])
    found_episode_numbers = set()
    
    if valid_eps:
        buckets = {}
        for ep_num, file_data in valid_eps:
            found_episode_numbers.add(int(ep_num) if ep_num % 1 == 0 else ep_num)
            
            # ✅ THIS IS YOUR ORIGINAL LOGIC FOR BATCHES OF 5
            b_idx = (int(ep_num) - 1) // 5 
            
            if b_idx not in buckets: buckets[b_idx] = []
            buckets[b_idx].append(file_data)
            
        sorted_indices = sorted(buckets.keys())
        for idx in sorted_indices:
            # Calculate batch number: batch1, batch2...
            batch_name = f"batch{idx + 1}"
            sorted_batch = sorted(buckets[idx], key=lambda x: x['name'])
            batches[batch_name] = sorted_batch

    missing_list = []
    if valid_eps:
        max_ep = int(valid_eps[-1][0])
        full_range = set(range(1, max_ep + 1))
        found_ints = {int(x) for x in found_episode_numbers if x % 1 == 0}
        missing_set = full_range - found_ints
        missing_list = sorted(list(missing_set))

    if unmatched: batches["batch_uncategorized"] = unmatched
    return batches, missing_list

# ================= UTILS (SAME AS ORIGINAL) =================
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

def github_update_json(data):
    if not GITHUB_TOKEN or "YOUR_GITHUB" in GITHUB_TOKEN: return
    try:
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
    except Exception as e: print(f"GitHub Error: {e}")

# ================= SAVE & SCAN (SAME AS ORIGINAL) =================
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
    if not anime_meta: return
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
        merged_ids = existing_ids.union(incoming_ids)
        season_node["mal_ids"] = sorted(list(merged_ids))

    if "languages" not in season_node: season_node["languages"] = {}
    season_node["languages"][lang] = {
        "batches": episodes,
        "specials": specials
    }

async def process_season_block(meta, collected_files, index, ai_handler):
    if not meta or not collected_files: return
    print(f"🤖 Processing {len(collected_files)} files for {meta['title']}...")
    
    ai_results = ai_handler.process_season(collected_files, meta)
    
    ep_dict_raw = {}
    sp_dict = {}
    un_list = []

    for file_obj in collected_files:
        msg_id = file_obj['file_id']
        entry = {
            "file": msg_id, 
            "channel_id": file_obj['channel_id'],
            "name": file_obj['name']
        }
        
        if msg_id in ai_results:
            result = ai_results[msg_id]
            if result['type'] == 'episode': ep_dict_raw[str(result['num'])] = entry
            elif result['type'] == 'special': sp_dict[result.get('name', 'Special')] = entry
            else: un_list.append(entry)
        else: un_list.append(entry)

    final_batches, missing_eps = build_batches(ep_dict_raw, un_list)
    UPDATE_PROGRESS["processed"] += len(collected_files)
    save_anime_to_index(meta, final_batches, sp_dict, un_list, index, missing_eps)

async def scan_channel(client, channel_id, index, state, force_rescan=False):
    last_id = 0 if force_rescan else state.get(str(channel_id), 0)
    curr_meta = None
    curr_files = []
    ai_handler = BulkAIHandler()
    print(f"🚀 Scanning {channel_id} from {last_id}")

    async for msg in client.iter_messages(channel_id, min_id=last_id, reverse=True):
        text = msg.text or ""
        
        if "</START>" in text:
            if curr_meta: await process_season_block(curr_meta, curr_files, index, ai_handler)
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
                "file_id": msg.id,
                "channel_id": channel_id,
                "name": msg.file.name or "Unknown",
                "caption": text or ""
            })
            state[str(channel_id)] = msg.id

    if curr_meta: await process_season_block(curr_meta, curr_files, index, ai_handler)
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
        await event.reply("☢️ AI Force Update..." if force else "🔄 AI Updating...")
        UPDATE_PROGRESS["processed"] = 0
        try:
            for ch in CHANNELS: await scan_channel(client, ch, index, state, force_rescan=force)
            save_json(JSON_FILE, index)
            github_update_json(index)
            await event.reply(f"✅ AI Done! Processed: {UPDATE_PROGRESS['processed']}")
        except Exception as e:
            await event.reply(f"❌ Error: {e}")
            import traceback; traceback.print_exc()
            
    print("🤖 AI Bot Active. Send '/update force'")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())