import re
import json
import asyncio
import os
import base64
import time
import requests
from google import genai
from google.genai import types
from telethon import TelegramClient, events

# ================= TELEGRAM CONFIG =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
SESSION_NAME = "anime_indexer"

CHANNELS = [
    -1003175788400,
    -1003498912074
]
ADMIN_IDS = [8466952185] 

# ================= AI CONFIG =================
GEMINI_API_KEYS = [
   "AIzaSyBXx2n-0Oq2LF3VjC8YCLNO_eAoH2A9Jc4" , "AIzaSyC_Rbz07Mdrp5xzAJQCwvc_Sy2fI95C6tY", "AIzaSyDAbTFURmul-ZQNcSzG15XUG1T3MBB6lN4"
]

# This alias points to the best available free model (currently 1.5 Flash)
MODEL_NAME = "gemini-flash-latest"

current_key_index = 0
AI_AVAILABLE = False
client = None

def configure_ai():
    global AI_AVAILABLE, client, current_key_index
    if not GEMINI_API_KEYS:
        AI_AVAILABLE = False
        return
    try:
        client = genai.Client(api_key=GEMINI_API_KEYS[current_key_index])
        AI_AVAILABLE = True
        print(f"🔑 AI Initialized with Key #{current_key_index + 1} ({MODEL_NAME})")
    except Exception as e:
        print(f"❌ AI Init Error: {e}")
        AI_AVAILABLE = False

def rotate_key():
    """
    Switches to next key. 
    RETURNS FALSE if there is only 1 key (signals the bot to sleep).
    """
    global current_key_index, client
    if not GEMINI_API_KEYS: return False
    
    # CRITICAL FIX: If only 1 key, force sleep instead of infinite retry
    if len(GEMINI_API_KEYS) <= 1:
        return False

    prev_index = current_key_index
    current_key_index = (current_key_index + 1) % len(GEMINI_API_KEYS)
    new_key = GEMINI_API_KEYS[current_key_index]
    
    print(f"🔄 Switching Key #{prev_index + 1} -> #{current_key_index + 1}...")
    try:
        client = genai.Client(api_key=new_key)
        if current_key_index == 0:
            return False
        return True
    except:
        return False

configure_ai()

# ================= FILES & GITHUB =================
JSON_FILE = "anime_index.json"
STATE_FILE = "scan_state.json"
GITHUB_TOKEN = "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" 
GITHUB_OWNER = "ayarsbusiness-bot"
GITHUB_REPO = "anime-index"
GITHUB_BRANCH = "main"
GITHUB_FILE = "anime_index.json"

# ================= BULK AI HANDLER =================
class BulkAIHandler:
    def process_season(self, files, season_num):
        if not AI_AVAILABLE or not files: 
            print("⚠️ AI Not Available or No Files. Skipping.")
            return {}

        files.sort(key=lambda x: x['name'])
        prompt = self._build_prompt(files, season_num)
        
        response_list = self._call_ai_with_rotation(prompt)
        
        final_mapping = {}
        if response_list:
            for item in response_list:
                try:
                    msg_id = int(item["id"].replace("ID_", ""))
                    final_mapping[msg_id] = item
                except: continue
        return final_mapping

    def _build_prompt(self, files, season):
        files_text = ""
        for file in files:
            clean_name = file['name']
            clean_caption = file['caption'].replace('\n', ' ')[:100] 
            files_text += f"ID_{file['file_id']}: Name='{clean_name}', Caption='{clean_caption}'\n"

        return f"""
        You are an Anime Indexing Bot. 
        I have a list of files for **Season {season}**.
        
        DATA:
        {files_text}

        TASK:
        1. Identify the Episode Number for each file based on its Name/Caption.
        2. If it is a Special/OVA, mark type as "special".
        3. If a file belongs to a DIFFERENT season (e.g. S{int(season)+1}), mark it as "ignore".
        4. Return a JSON List.

        OUTPUT FORMAT (Strict JSON):
        [
            {{"id": "ID_12345", "type": "episode", "num": 1}},
            {{"id": "ID_67890", "type": "special", "name": "OVA 1"}}
        ]
        """

    def _call_ai_with_rotation(self, prompt):
        while True:
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt
                )
                
                clean_text = response.text.replace('```json', '').replace('```', '').strip()
                return json.loads(clean_text)
            
            except Exception as e:
                error_str = str(e).lower()
                
                # Handle Rate Limits (429)
                if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                    print(f"⏳ Quota Hit.", end=" ")
                    
                    switched = rotate_key()
                    
                    if switched:
                        print("Retrying with new key...")
                        time.sleep(1)
                    else:
                        # If we have only 1 key (or all used), SLEEP 60s
                        print("Waiting 60s for quota reset...")
                        time.sleep(60) 
                    continue
                
                else:
                    print(f"⚠️ AI Error: {e}")
                    return []

# ================= UTILS =================
def build_batches(episodes, unmatched):
    batches = {}
    valid_eps = []
    
    # 1. Sort Episodes
    for num_str, data in episodes.items():
        try:
            valid_eps.append((int(num_str), data))
        except:
            unmatched.append(data)
    
    valid_eps.sort(key=lambda x: x[0])
    
    # 2. Strict Batching (1-5, 6-10...)
    if valid_eps:
        max_ep = valid_eps[-1][0]
        total_batches_needed = (max_ep + 4) // 5 
        
        for b_idx in range(total_batches_needed):
            batch_num = b_idx + 1
            start = (b_idx * 5) + 1
            end = start + 4
            
            current_batch_files = []
            has_files = False
            
            for i in range(start, end + 1):
                file_data = next((item[1] for item in valid_eps if item[0] == i), None)
                if file_data:
                    current_batch_files.append(file_data)
                    has_files = True
            
            if has_files:
                current_batch_files.sort(key=lambda x: x['name'])
                batches[f"batch{batch_num}"] = current_batch_files

    if unmatched: 
        batches["batch_uncategorized"] = unmatched
        
    return batches

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
    except Exception as e:
        print(f"GitHub Error: {e}")

# ================= SAVE & SCAN =================
def find_title_by_mal_id(index, mal_ids_to_check, season_num):
    if not mal_ids_to_check: return None
    target_ids = set(str(x) for x in mal_ids_to_check)
    for title, data in index.items():
        if "seasons" not in data: continue
        if season_num in data["seasons"]:
            season_data = data["seasons"][season_num]
            existing_ids = set(str(x) for x in season_data.get("mal_ids", []))
            if not target_ids.isdisjoint(existing_ids):
                return title
    return None

def save_anime_to_index(anime_meta, episodes, specials, unmatched, index):
    if not anime_meta: return
    
    existing_title = find_title_by_mal_id(index, anime_meta["mal_ids"], anime_meta["season"])
    title = existing_title if existing_title else anime_meta["title"]
    season = anime_meta["season"]
    lang = anime_meta["language"] or "Unknown"

    print(f"💾 Saving: {title} S{season} [{lang}]")

    if title not in index: index[title] = {"seasons": {}}
    if season not in index[title]["seasons"]:
        index[title]["seasons"][season] = {"total_episodes": anime_meta["total"], "mal_ids": [], "languages": {}}
    
    season_node = index[title]["seasons"][season]
    existing_ids = set(str(x) for x in season_node.get("mal_ids", []))
    incoming_ids = set(str(x) for x in anime_meta.get("mal_ids", []))
    if incoming_ids:
        merged_ids = existing_ids.union(incoming_ids)
        season_node["mal_ids"] = sorted(list(merged_ids))

    if "languages" not in season_node: season_node["languages"] = {}
    
    final_batches = build_batches(episodes, unmatched)
    season_node["languages"][lang] = {"batches": final_batches, "specials": specials}

async def process_season_block(meta, collected_files, index, ai_handler):
    if not meta or not collected_files: return
    print(f"🤖 Processing {len(collected_files)} files for {meta['title']}...")
    
    ai_results = ai_handler.process_season(collected_files, meta["season"])
    
    ep_dict, sp_dict, un_list = {}, {}, []
    for file_obj in collected_files:
        msg_id = file_obj['file_id']
        if msg_id in ai_results:
            result = ai_results[msg_id]
            entry = {"file": msg_id, "name": file_obj['name']}
            
            if result['type'] == 'episode':
                ep_dict[str(result['num'])] = entry
            elif result['type'] == 'special':
                sp_name = result.get('name', 'Special')
                sp_dict[sp_name] = entry
            elif result['type'] == 'ignore':
                pass 
            else:
                un_list.append(entry)
        else:
            un_list.append({"file": msg_id, "name": file_obj['name']})

    UPDATE_PROGRESS["processed"] += len(collected_files)
    save_anime_to_index(meta, ep_dict, sp_dict, un_list, index)

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
                curr_meta = {"title": tm.group(1).strip(), "season": sm.group(1).strip(), "language": lm.group(1).strip() if lm else "Unknown", "total": int(total_m.group(1)) if total_m else 0, "mal_ids": mal_ids}
                curr_files = []
            state[str(channel_id)] = msg.id
            continue

        if curr_meta and msg.file:
            curr_files.append({"file_id": msg.id, "name": msg.file.name or "Unknown", "caption": text or ""})
            state[str(channel_id)] = msg.id

    if curr_meta: await process_season_block(curr_meta, curr_files, index, ai_handler)
    save_json(STATE_FILE, state)

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