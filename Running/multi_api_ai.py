import re
import json
import asyncio
import os
import time
import requests
import base64
from groq import Groq
from telethon import TelegramClient, events

# ================= CONFIGURATION =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
SESSION_NAME = "anime_indexer"

# 🔴 ADD YOUR MULTIPLE GROQ KEYS HERE
GROQ_API_KEYS = [
    "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",
   "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"
]

CHANNELS = [-1003175788400, -1003498912074]
ADMIN_IDS = [8466952185] 

MODEL_NAME = "llama-3.3-70b-versatile" 
AUDIT_DIR = "ai_audit_logs"

# ================= SETUP =================
if not os.path.exists(AUDIT_DIR):
    os.makedirs(AUDIT_DIR)

AI_AVAILABLE = False
client = None
CURRENT_KEY_INDEX = 0

def configure_ai():
    global AI_AVAILABLE, client, CURRENT_KEY_INDEX
    if not GROQ_API_KEYS:
        AI_AVAILABLE = False
        return
    try:
        # Initialize with the current key index
        client = Groq(api_key=GROQ_API_KEYS[CURRENT_KEY_INDEX])
        AI_AVAILABLE = True
        print(f"✅ Groq AI Initialized (Key Index: {CURRENT_KEY_INDEX})")
    except Exception as e:
        print(f"❌ Groq Init Error: {e}")
        AI_AVAILABLE = False

def rotate_client():
    """Switches to the next API key in the list."""
    global client, CURRENT_KEY_INDEX, AI_AVAILABLE
    if not GROQ_API_KEYS: return False
    
    # Increment index, wrapping around
    prev_index = CURRENT_KEY_INDEX
    CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % len(GROQ_API_KEYS)
    
    print(f"⚠️ Switching API Key: {prev_index} -> {CURRENT_KEY_INDEX}")
    try:
        client = Groq(api_key=GROQ_API_KEYS[CURRENT_KEY_INDEX])
        return True
    except Exception as e:
        print(f"❌ Error rotating key: {e}")
        return False

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

# ================= 1. REGEX ENGINE (LEVEL 1) =================
class RegexEngine:
    @staticmethod
    def extract_episode(text):
        """
        Tries to extract episode number using strict patterns.
        Returns: (start_num, end_num) or None
        """
        clean_text = text.replace("\n", " ").strip()
        
        # Pattern 1: S01E05 or S01E05-06
        s_match = re.search(r"S\d+E(\d+)(?:-E?(\d+))?", clean_text, re.IGNORECASE)
        if s_match:
            start = float(s_match.group(1))
            end = float(s_match.group(2)) if s_match.group(2) else start
            return start, end

        # Pattern 2: Episode 05 or Ep.05
        ep_match = re.search(r"(?:Episode|Ep|E)\.?\s*(\d+)(?:-?(\d+))?", clean_text, re.IGNORECASE)
        if ep_match:
            start = float(ep_match.group(1))
            end = float(ep_match.group(2)) if ep_match.group(2) else start
            return start, end

        # Pattern 3: " - 05 " (Hyphen separator)
        # Avoids "2024" or "720p" by checking boundaries
        hyphen_match = re.search(r"\s-\s(\d{1,3})(?:\s|\[|\.)", clean_text)
        if hyphen_match:
            return float(hyphen_match.group(1)), float(hyphen_match.group(1))

        return None

# ================= 2. HYBRID HANDLER (LEVEL 2) =================
class HybridHandler:
    def process_season(self, files, meta):
        final_mapping = {}
        files_for_ai = []

        print(f"🔍 Hybrid Scan: {len(files)} files for {meta['title']}...")

        # STEP 1: Strict Regex Scan (Fast & Accurate)
        for file in files:
            # Check Caption FIRST, then Name
            sources = [file['caption'], file['name']]
            found = False
            
            for text in sources:
                if not text: continue
                result = RegexEngine.extract_episode(text)
                if result:
                    start, end = result
                    final_mapping[file['file_id']] = {
                        "id": f"ID_{file['file_id']}",
                        "type": "episode",
                        "num": start,
                        "end_num": end
                    }
                    found = True
                    break # Found it, stop checking sources
            
            if not found:
                files_for_ai.append(file)

        # STEP 2: Use AI only for "Garbage" filenames
        if files_for_ai and AI_AVAILABLE:
            print(f"⚠️ Regex missed {len(files_for_ai)} files. Sending to AI...")
            # NO CHUNKING: Send all remaining files at once for full context
            ai_results = self._process_with_groq(files_for_ai, meta)
            
            # Merge AI results
            for fid, result in ai_results.items():
                final_mapping[fid] = result
        
        return final_mapping

    def _process_with_groq(self, files, meta):
        # Build Prompt
        files_text = ""
        for file in files:
            clean_name = file['name']
            clean_caption = file['caption'].replace('\n', ' ')[:300]
            files_text += f"ID_{file['file_id']}: Caption='{clean_caption}' Name='{clean_name}'\n"

        prompt = f"""
        You are an Anime Indexing Bot.
        Target: "{meta['title']}" (Season {meta['season']})

        Task: Identify Episode Numbers for these tricky files.
        
        RULES:
        1. **Look Deep:** The number might be hidden like "Part 1" (Ep 1) or "Final" (Last Ep).
        2. **Multi-Episode:** If "01-02", return "num": 1, "end_num": 2.
        3. **Ignore:** If it's a trailer, opening song, or unrelated, return "type": "ignore".

        DATA:
        {files_text}

        OUTPUT JSON:
        {{ "files": [ 
            {{ "id": "ID_...", "type": "episode", "num": 1 }},
            {{ "id": "ID_...", "type": "episode", "num": 1, "end_num": 2 }} 
        ] }}
        """
        
        # --- API KEY ROTATION LOGIC START ---
        max_attempts = len(GROQ_API_KEYS)
        for attempt in range(max_attempts):
            try:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    model=MODEL_NAME, temperature=0.1, response_format={"type": "json_object"}
                )
                response = json.loads(chat_completion.choices[0].message.content)
                
                # Parse response
                mapping = {}
                items = response if isinstance(response, list) else response.get("files", [])
                for item in items:
                    try:
                        msg_id = int(str(item["id"]).replace("ID_", ""))
                        mapping[msg_id] = item
                    except: continue
                return mapping

            except Exception as e:
                print(f"❌ AI Error (Key {CURRENT_KEY_INDEX}): {e}")
                # If this was the last attempt, return empty
                if attempt == max_attempts - 1:
                    print("❌ All API keys exhausted or failed.")
                    return {}
                # Otherwise, rotate and try again
                rotate_client()
                time.sleep(1) # Short delay before retry
        # --- API KEY ROTATION LOGIC END ---
        
        return {}

# ================= 3. BATCHING & REPAIR (LEVEL 3) =================
def build_batches_with_repair(episodes_list, unmatched_raw):
    batches = {}
    valid_eps = []
    covered_numbers = set()

    # 1. Process Valid Episodes
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
            unmatched_raw.append(data) # Should not happen often

    # 2. Sort
    valid_eps.sort(key=lambda x: x[0])

    # 3. Create Batches (Size 5)
    if valid_eps:
        buckets = {}
        for ep_num, file_data in valid_eps:
            b_idx = (int(ep_num) - 1) // 5
            if b_idx not in buckets: buckets[b_idx] = []
            buckets[b_idx].append(file_data)
            
        for idx in sorted(buckets.keys()):
            batches[f"batch{idx + 1}"] = sorted(buckets[idx], key=lambda x: x['name'])

    # 4. Calculate Missing
    missing_list = []
    if valid_eps:
        max_ep = int(max([x[0] for x in valid_eps] + list(covered_numbers)))
        full_range = set(range(1, max_ep + 1))
        missing_list = sorted(list(full_range - covered_numbers))

    # 5. Add Uncategorized
    if unmatched_raw:
        # Simple cleanup of unmatched list to remove AI artifacts
        clean_unmatched = []
        for u in unmatched_raw:
            clean_unmatched.append({k:v for k,v in u.items() if k not in ['num', 'type']})
        batches["batch_uncategorized"] = clean_unmatched

    return batches, missing_list

# ================= 4. SUMMARY GENERATOR =================
def generate_availability_summary(index_data):
    summary = []
    print("📊 Generating Availability Summary...")
    
    for title, data in index_data.items():
        if "seasons" not in data: continue
        
        anime_entry = {"title": title, "mal_ids": [], "languages": []}
        all_mal_ids = set()
        all_langs = set()
        
        for season, s_data in data["seasons"].items():
            if "mal_ids" in s_data:
                for mid in s_data["mal_ids"]: all_mal_ids.add(str(mid))
            if "languages" in s_data:
                for lang in s_data["languages"].keys(): all_langs.add(lang)
        
        anime_entry["mal_ids"] = sorted(list(all_mal_ids))
        anime_entry["languages"] = sorted(list(all_langs))
        summary.append(anime_entry)
    
    try:
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        return summary
    except: return []

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
    
    # 1. Use Hybrid Handler (Regex First, AI Second)
    mapping_results = handler.process_season(collected_files, meta)
    
    ep_list_raw = []
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
            else:
                un_list.append(entry)
        else:
            un_list.append(entry)

    # 2. Build Batches
    final_batches, missing_eps = build_batches_with_repair(ep_list_raw, un_list)
    
    UPDATE_PROGRESS["processed"] += len(collected_files)
    save_anime_to_index(meta, final_batches, {}, un_list, index, missing_eps)

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