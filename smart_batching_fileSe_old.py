import re
import json
import asyncio
import os
import time
import requests
import base64
from telethon import TelegramClient, events

# ================= CONFIGURATION =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
SESSION_NAME = "anime_indexer"

CHANNELS = [-1003175788400, -1003498912074]
ADMIN_IDS = [8466952185] 

# ================= FILES & DATA =================
JSON_FILE = "anime_index.json"
SUMMARY_FILE = "available_animes.json"
STATE_FILE = "scan_state.json"
GITHUB_TOKEN = "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" 
GITHUB_OWNER = "ayarsbusiness-bot"
GITHUB_REPO = "anime-index"
GITHUB_BRANCH = "main"
GITHUB_FILE = "anime_index.json"

# ================= 1. REGEX ENGINE =================
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

# ================= 2. HYBRID HANDLER (NO AI) =================
class HybridHandler:
    def process_season(self, files, meta):
        final_mapping = {}
        
        print(f"🔍 Scan: {len(files)} files for {meta['title']}...")

        # Sort files by ID (Earliest Message = First Episode usually)
        # This ensures the sequence fallback works correctly
        sorted_files = sorted(files, key=lambda x: x['file_id'])

        current_sequence_num = 1.0

        for file in sorted_files:
            # Check Caption FIRST, then Name
            sources = [file['caption'], file['name']]
            found = False
            
            # 1. Try Regex
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
                    # Update sequence counter to follow this match
                    # e.g., if we found Ep 5, next likely is 6
                    current_sequence_num = end + 1.0
                    found = True
                    break 
            
            # 2. Sequence Fallback (If Regex Failed)
            if not found:
                final_mapping[file['file_id']] = {
                    "id": f"ID_{file['file_id']}",
                    "type": "episode",
                    "num": current_sequence_num,
                    "end_num": current_sequence_num
                }
                # Increment for the next file
                current_sequence_num += 1.0
        
        return final_mapping

# ================= 3. BATCHING & REPAIR =================
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
            
            # We keep 'name' temporarily for sorting purposes only
            clean_data = {k:v for k,v in data.items() if k not in ['num', 'end_num', 'type']}
            valid_eps.append((start_num, clean_data))
        except: 
            unmatched_raw.append(data) 

    # 2. Sort by episode number
    valid_eps.sort(key=lambda x: x[0])

    # 3. Create Batches (Size 10)
    if valid_eps:
        buckets = {}
        for ep_num, file_data in valid_eps:
            # Batching by 10 (0-9 -> batch1, 10-19 -> batch2, etc.)
            b_idx = (int(ep_num) - 1) // 10
            if b_idx not in buckets: buckets[b_idx] = []
            buckets[b_idx].append(file_data)
            
        for idx in sorted(buckets.keys()):
            # Sort internally by name (if it exists) before removing it
            sorted_items = sorted(buckets[idx], key=lambda x: x.get('name', ''))
            
            # Remove 'name' key from final output to reduce size
            minified_items = [{k: v for k, v in item.items() if k != 'name'} for item in sorted_items]
            
            batches[f"batch{idx + 1}"] = minified_items

    # 4. Calculate Missing
    missing_list = []
    if valid_eps:
        max_ep = int(max([x[0] for x in valid_eps] + list(covered_numbers)))
        full_range = set(range(1, max_ep + 1))
        missing_list = sorted(list(full_range - covered_numbers))

    # 5. Add Uncategorized
    if unmatched_raw:
        clean_unmatched = []
        for u in unmatched_raw:
            # Remove 'name' from uncategorized as well
            item = {k:v for k,v in u.items() if k not in ['num', 'type', 'name']}
            clean_unmatched.append(item)
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
SEASON_RE = re.compile(r"Season\s*:\s*(.+)", re.I)
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
def find_title_by_mal_id(index, mal_ids_to_check, season_key):
    if not mal_ids_to_check: return None
    target_ids = set(str(x) for x in mal_ids_to_check)
    for title, data in index.items():
        if "seasons" not in data: continue
        if season_key in data["seasons"]:
            season_data = data["seasons"][season_key]
            existing_ids = set(str(x) for x in season_data.get("mal_ids", []))
            if not target_ids.isdisjoint(existing_ids): return title
    return None

def save_anime_to_index(anime_meta, episodes, specials, unmatched, index, missing_eps):
    # 1. Resolve Title
    existing_title = find_title_by_mal_id(index, anime_meta["mal_ids"], anime_meta["season"])
    title = existing_title if existing_title else anime_meta["title"]
    
    # 2. Get Raw Season Name
    raw_season_name = str(anime_meta["season"]).strip()
    lang = anime_meta["language"] or "Unknown"

    print(f"💾 Saving: {title} -> {raw_season_name} [{lang}]")

    if title not in index: index[title] = {"seasons": {}}
    
    # ================= DUPLICATE CHECKER START =================
    final_season_name = raw_season_name
    
    def extract_file_ids(batch_dict):
        ids = set()
        for b_list in batch_dict.values():
            for item in b_list:
                if 'file' in item and 'channel_id' in item:
                    ids.add(f"{item['channel_id']}:{item['file']}")
        return ids

    def extract_file_ids_list(u_list):
        ids = set()
        for item in u_list:
            if 'file' in item and 'channel_id' in item:
                ids.add(f"{item['channel_id']}:{item['file']}")
        return ids

    incoming_ids = extract_file_ids(episodes)
    incoming_ids.update(extract_file_ids_list(unmatched))

    found_existing_season = None

    if incoming_ids:
        for s_name, s_data in index[title]["seasons"].items():
            existing_ids = set()
            if "languages" in s_data:
                for l_data in s_data["languages"].values():
                    if "batches" in l_data:
                        existing_ids.update(extract_file_ids(l_data["batches"]))
                    if "specials" in l_data:
                        existing_ids.update(extract_file_ids(l_data["specials"]))
            
            if not incoming_ids.isdisjoint(existing_ids):
                found_existing_season = s_name
                break
    
    if found_existing_season:
        print(f"🔄 Found existing files in season '{found_existing_season}'. Updating entry instead of Mirroring.")
        final_season_name = found_existing_season
    
    # ================= DUPLICATE CHECKER END =================

    elif final_season_name in index[title]["seasons"]:
        mirror_count = 1
        while True:
            if raw_season_name.isdigit():
                base_name = f"S{raw_season_name}" 
            else:
                base_name = raw_season_name 

            if mirror_count == 1:
                candidate = f"{base_name} Mirror" 
            else:
                candidate = f"{base_name} Mirror {mirror_count}" 

            if candidate not in index[title]["seasons"]:
                final_season_name = candidate
                break
            mirror_count += 1
        
        print(f"⚠️ Conflict found. Saved as new entry: '{final_season_name}'")

    if final_season_name not in index[title]["seasons"]:
        index[title]["seasons"][final_season_name] = {
            "total_episodes": anime_meta["total"], 
            "mal_ids": anime_meta["mal_ids"], 
            "languages": {}, 
            "missing_episodes": []
        }

    season_node = index[title]["seasons"][final_season_name]
    
    if anime_meta["total"] > 0: season_node["total_episodes"] = anime_meta["total"]
    
    current_ids = set(season_node.get("mal_ids", []))
    for mid in anime_meta["mal_ids"]: current_ids.add(mid)
    season_node["mal_ids"] = list(current_ids)
    
    season_node["languages"][lang] = {
        "batches": episodes, 
        "specials": specials
    }
    
    season_node["missing_episodes"] = missing_eps

async def process_season_block(meta, collected_files, index, handler):
    if not meta or not collected_files: return
    
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
                    "title": tm.group(1).strip(), 
                    "season": sm.group(1).strip(),
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
        await event.reply("☢️ Indexer Starting (No AI)..." if force else "🔄 Updating...")
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
            
    print("🤖 Bot Active (Regex + Sequence Fallback).")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())