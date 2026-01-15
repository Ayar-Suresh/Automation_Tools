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

# 🔴 PASTE YOUR GROQ KEY HERE
GROQ_API_KEY = "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" 

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

# ================= 1. REGEX ENGINE (LEVEL 1) =================
class RegexEngine:
    @staticmethod
    def extract_episode(text):
        """
        Tries to extract episode number using strict patterns.
        Returns: (start_num, end_num) or None
        """
        if not text:
            return None
            
        clean_text = text.replace("\n", " ").strip()
        
        # Pattern 1: S01E05 or S01E05-06
        s_match = re.search(r"S\d+E(\d+)(?:-E?(\d+))?", clean_text, re.IGNORECASE)
        if s_match:
            start = float(s_match.group(1))
            end = float(s_match.group(2)) if s_match.group(2) else start
            return start, end

        # Pattern 2: Episode 05, Ep.05, E01, Episode - 05, Episode-05
        ep_match = re.search(r"(?:Episode|Ep|E)\s*-?\s*(\d{1,3})(?:-(\d{1,3}))?", clean_text, re.IGNORECASE)
        if ep_match:
            start = float(ep_match.group(1))
            end = float(ep_match.group(2)) if ep_match.group(2) else start
            return start, end

        # Pattern 3: Underscore-separated numbers: _01_, _02_, etc.
        underscore_match = re.search(r"_(\d{1,3})_(?:[^\d]|$)", clean_text)
        if underscore_match:
            num = float(underscore_match.group(1))
            # Only accept if it's a reasonable episode number (1-999)
            if 1 <= num <= 999:
                return num, num

        # Pattern 4: " - 05 " (Hyphen separator with spaces)
        # More flexible: handles "Episode - 05" or " - 05 "
        hyphen_match = re.search(r"(?:Episode|Ep)?\s*-\s*(\d{1,3})(?:\s|\[|\.|\)|$)", clean_text, re.IGNORECASE)
        if hyphen_match:
            num = float(hyphen_match.group(1))
            if 1 <= num <= 999:
                return num, num

        # Pattern 5: Simple numeric filenames (fallback): "9.mkv", "10.mkv", "001.mp4"
        # Only match if it's the entire filename or clearly an episode number
        simple_num_match = re.search(r"^(\d{1,3})\.(mkv|mp4|avi|mov|webm)$", clean_text, re.IGNORECASE)
        if simple_num_match:
            num = float(simple_num_match.group(1))
            if 1 <= num <= 999:
                return num, num

        # Pattern 6: Numbers at start/end with common separators: "01.", "01-", "-01"
        # But avoid matching quality indicators like "720p", "1080p"
        boundary_match = re.search(r"(?:^|[^\d])(\d{1,3})(?:\.(?:mkv|mp4|avi|mov|webm)|-[^\dp]|$)", clean_text, re.IGNORECASE)
        if boundary_match:
            num = float(boundary_match.group(1))
            # More strict: only if it's likely an episode (not year, quality, etc.)
            # Avoid common quality numbers
            if 1 <= num <= 200 and num not in [720, 1080, 480, 360]:  # Reasonable episode range, exclude common resolutions
                return num, num

        return None

# ================= 2. HYBRID HANDLER (LEVEL 2) =================
class HybridHandler:
    def __init__(self):
        self.validation_errors = []
    
    def _validate_episode_number(self, num, file_id, source="unknown"):
        """Validate episode number is within reasonable range"""
        try:
            num_float = float(num)
            if num_float < 0 or num_float > 1000:
                self.validation_errors.append(f"Invalid episode number {num} for file {file_id} from {source}")
                return None
            return num_float
        except (ValueError, TypeError):
            self.validation_errors.append(f"Non-numeric episode {num} for file {file_id} from {source}")
            return None
    
    def process_season(self, files, meta):
        final_mapping = {}
        files_for_ai = []
        self.validation_errors = []

        print(f"🔍 Hybrid Scan: {len(files)} files for {meta['title']}...")

        # STEP 1: Strict Regex Scan (Fast & Accurate)
        for file in files:
            # Check Caption FIRST, then Name
            sources = [("caption", file['caption']), ("name", file['name'])]
            found = False
            
            for source_type, text in sources:
                if not text: continue
                result = RegexEngine.extract_episode(text)
                if result:
                    start, end = result
                    # Validate episode numbers
                    start_valid = self._validate_episode_number(start, file['file_id'], source_type)
                    end_valid = self._validate_episode_number(end, file['file_id'], source_type)
                    
                    if start_valid is not None and end_valid is not None:
                        # Ensure start <= end
                        if start_valid > end_valid:
                            start_valid, end_valid = end_valid, start_valid
                        
                        final_mapping[file['file_id']] = {
                            "id": f"ID_{file['file_id']}",
                            "type": "episode",
                            "num": start_valid,
                            "end_num": end_valid,
                            "source": source_type  # Track where we got it from
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
            
            # Merge AI results with validation
            for fid, result in ai_results.items():
                if result.get('type') == 'episode':
                    num = self._validate_episode_number(result.get('num'), fid, "AI")
                    end_num = self._validate_episode_number(result.get('end_num', result.get('num')), fid, "AI")
                    
                    if num is not None and end_num is not None:
                        if num > end_num:
                            num, end_num = end_num, num
                        result['num'] = num
                        result['end_num'] = end_num
                        result['source'] = 'AI'
                        final_mapping[fid] = result
                    else:
                        # Invalid episode number from AI, treat as unmatched
                        print(f"⚠️ AI returned invalid episode number for file {fid}, treating as unmatched")
                else:
                    # Type is 'ignore' or something else, keep it
                    final_mapping[fid] = result
        
        if self.validation_errors:
            print(f"⚠️ Validation warnings: {len(self.validation_errors)} issues found")
            for err in self.validation_errors[:5]:  # Show first 5
                print(f"   - {err}")
        
        return final_mapping

    def _process_with_groq(self, files, meta, retry_count=2):
        # Build Prompt
        files_text = ""
        for file in files:
            clean_name = file['name'] or "Unknown"
            clean_caption = (file['caption'] or "").replace('\n', ' ')[:500]
            files_text += f"ID_{file['file_id']}: Caption='{clean_caption}' Name='{clean_name}'\n"

        prompt = f"""
        You are an Anime Indexing Bot.
        Target: "{meta['title']}" (Season {meta['season']})

        Task: Identify Episode Numbers for these files that regex couldn't match.
        
        CRITICAL RULES:
        1. **PRIORITIZE CAPTION:** The caption often has "Episode - XX" or "Episode: XX" - extract from there FIRST.
        2. **Filename Patterns:** Look for patterns like:
           - "Episode XX", "Ep XX", "EXX", "Episode - XX"
           - "_XX_", "XX.mkv", "XX.mp4"
           - "season X episode XX"
        3. **Simple Numbers:** If filename is just "9.mkv" or "10.mkv", use that number.
        4. **Multi-Episode:** If "01-02" or "Ep 1-2", return "num": 1, "end_num": 2.
        5. **Be Aggressive:** If you see ANY clear episode indicator (even in caption), extract it.
        6. **Ignore Only:** Return "type": "ignore" ONLY if it's clearly a trailer, opening song, or completely unrelated.
        7. **Episode Range:** Episode numbers must be between 1-1000. If you see "Episode - 01", extract 1, not 01 as string.

        DATA:
        {files_text}

        OUTPUT JSON:
        {{ "files": [ 
            {{ "id": "ID_...", "type": "episode", "num": 1 }},
            {{ "id": "ID_...", "type": "episode", "num": 1, "end_num": 2 }},
            {{ "id": "ID_...", "type": "ignore" }}
        ] }}
        
        IMPORTANT: Extract episode numbers aggressively. If caption says "Episode - 01" or filename has "_01_", extract it!
        Return numeric values for "num" and "end_num", not strings.
        """
        
        for attempt in range(retry_count + 1):
            try:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You must return valid JSON only. Episode numbers must be numeric (1, 2, 3) not strings."},
                        {"role": "user", "content": prompt}
                    ],
                    model=MODEL_NAME, temperature=0.1, response_format={"type": "json_object"}
                )
                response_text = chat_completion.choices[0].message.content
                response = json.loads(response_text)
                
                # Validate response structure
                if not isinstance(response, dict):
                    raise ValueError("Response is not a dictionary")
                
                # Parse response with better error handling
                mapping = {}
                items = response if isinstance(response, list) else response.get("files", [])
                
                if not items:
                    print(f"⚠️ AI returned empty results for {len(files)} files")
                    return {}
                
                for item in items:
                    try:
                        if not isinstance(item, dict):
                            continue
                        item_id = item.get("id", "")
                        msg_id_str = str(item_id).replace("ID_", "").strip()
                        if not msg_id_str.isdigit():
                            continue
                        msg_id = int(msg_id_str)
                        
                        # Validate item structure
                        if item.get("type") == "episode":
                            num = item.get("num")
                            if num is None:
                                continue
                            # Ensure num is numeric
                            try:
                                num = float(num)
                                if num < 1 or num > 1000:
                                    continue
                            except (ValueError, TypeError):
                                continue
                            
                            end_num = item.get("end_num", num)
                            try:
                                end_num = float(end_num)
                                if end_num < 1 or end_num > 1000:
                                    end_num = num
                            except (ValueError, TypeError):
                                end_num = num
                            
                            mapping[msg_id] = {
                                "id": f"ID_{msg_id}",
                                "type": "episode",
                                "num": num,
                                "end_num": end_num
                            }
                        elif item.get("type") == "ignore":
                            mapping[msg_id] = {
                                "id": f"ID_{msg_id}",
                                "type": "ignore"
                            }
                    except (ValueError, KeyError, TypeError) as e:
                        continue
                
                if mapping:
                    print(f"✅ AI processed {len(mapping)}/{len(files)} files successfully")
                    return mapping
                else:
                    if attempt < retry_count:
                        print(f"⚠️ AI returned no valid results, retrying... ({attempt + 1}/{retry_count})")
                        time.sleep(1)
                        continue
                    else:
                        print(f"⚠️ AI failed to process files after {retry_count + 1} attempts")
                        return {}
                        
            except json.JSONDecodeError as e:
                print(f"❌ AI JSON Parse Error (attempt {attempt + 1}): {e}")
                if attempt < retry_count:
                    time.sleep(1)
                    continue
                return {}
            except Exception as e:
                print(f"❌ AI Error (attempt {attempt + 1}): {e}")
                if attempt < retry_count:
                    time.sleep(1)
                    continue
                return {}
        
        return {}

# ================= UTILS (needed by batching) =================
def natural_sort_key(key):
    """Natural sort key for sorting filenames with numbers"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(key))]

# ================= 3. BATCHING & REPAIR (LEVEL 3) =================
def build_batches_with_repair(episodes_list, unmatched_raw):
    batches = {}
    valid_eps = []
    covered_numbers = set()
    episode_to_files = {}  # Track which files map to which episodes (for duplicate detection)

    # 1. Process Valid Episodes with duplicate detection
    for data in episodes_list:
        try:
            start_num = float(data['num'])
            end_num = float(data.get('end_num', start_num))
            
            # Validate episode range
            if start_num < 1 or end_num < 1 or start_num > 1000 or end_num > 1000:
                print(f"⚠️ Skipping invalid episode range: {start_num}-{end_num} for file {data.get('file', 'unknown')}")
                unmatched_raw.append(data)
                continue
            
            if start_num > end_num:
                start_num, end_num = end_num, start_num  # Swap if reversed

            # Track episode coverage and detect duplicates
            curr = int(start_num)
            while curr <= int(end_num):
                if curr in episode_to_files:
                    # Duplicate episode detected - keep the one with better filename
                    existing_file = episode_to_files[curr]
                    current_file = data.get('name', '')
                    # Prefer files with more descriptive names (longer, contains episode info)
                    if len(current_file) > len(existing_file.get('name', '')) or 'episode' in current_file.lower():
                        # Replace with better match
                        episode_to_files[curr] = data
                        print(f"⚠️ Duplicate episode {curr}: Keeping better match '{current_file}'")
                else:
                    episode_to_files[curr] = data
                covered_numbers.add(curr)
                curr += 1
            
            clean_data = {k:v for k,v in data.items() if k not in ['num', 'end_num', 'type', 'source']}
            valid_eps.append((start_num, clean_data))
        except (ValueError, TypeError, KeyError) as e:
            print(f"⚠️ Error processing episode data: {e}, file: {data.get('file', 'unknown')}")
            unmatched_raw.append(data)

    # 2. Remove duplicates - keep only one file per episode number
    seen_episodes = set()
    deduplicated_eps = []
    for ep_num, file_data in valid_eps:
        ep_int = int(ep_num)
        if ep_int not in seen_episodes:
            seen_episodes.add(ep_int)
            deduplicated_eps.append((ep_num, file_data))
        else:
            print(f"⚠️ Removing duplicate episode {ep_int} from batch")
    
    valid_eps = deduplicated_eps

    # 3. Sort by episode number
    valid_eps.sort(key=lambda x: x[0])

    # 4. Create Batches (Size 5) with validation
    if valid_eps:
        buckets = {}
        for ep_num, file_data in valid_eps:
            b_idx = (int(ep_num) - 1) // 5
            if b_idx not in buckets: buckets[b_idx] = []
            buckets[b_idx].append(file_data)
            
        for idx in sorted(buckets.keys()):
            batch_name = f"batch{idx + 1}"
            batch_files = sorted(buckets[idx], key=lambda x: natural_sort_key(x.get('name', '')))
            
            # Validate batch size (should be <= 5, except last batch)
            if len(batch_files) > 5:
                print(f"⚠️ Batch {batch_name} has {len(batch_files)} files (expected max 5)")
            
            batches[batch_name] = batch_files

    # 5. Calculate Missing Episodes (more intelligent)
    missing_list = []
    if valid_eps and covered_numbers:
        max_ep = int(max([x[0] for x in valid_eps] + list(covered_numbers)))
        # Don't assume episodes go to 1000 - use actual max found
        if max_ep > 0:
            full_range = set(range(1, max_ep + 1))
            missing_list = sorted(list(full_range - covered_numbers))
            
            # Filter out unrealistic gaps (e.g., if we have ep 1-10 and ep 50, don't mark 11-49 as missing)
            # Only mark as missing if there are episodes before and after
            if missing_list:
                filtered_missing = []
                for missing_ep in missing_list:
                    # Check if there are episodes before and after this missing one
                    has_before = any(ep < missing_ep for ep in covered_numbers)
                    has_after = any(ep > missing_ep for ep in covered_numbers)
                    # Only include if it's in a reasonable range (within 50 episodes of existing episodes)
                    nearby_eps = [ep for ep in covered_numbers if abs(ep - missing_ep) <= 50]
                    if has_before and has_after and nearby_eps:
                        filtered_missing.append(missing_ep)
                missing_list = filtered_missing

    # 6. Add Uncategorized with cleanup
    if unmatched_raw:
        clean_unmatched = []
        seen_files = set()
        for u in unmatched_raw:
            # Remove AI artifacts and duplicates
            file_id = u.get('file')
            if file_id and file_id in seen_files:
                continue
            seen_files.add(file_id)
            
            clean_entry = {k:v for k,v in u.items() if k not in ['num', 'type', 'end_num', 'source']}
            if clean_entry:  # Only add if not empty
                clean_unmatched.append(clean_entry)
        
        if clean_unmatched:
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
            "total_episodes": anime_meta.get("total", 0), "mal_ids": [], "languages": {}, "missing_episodes": []
        }
    
    season_node = index[title]["seasons"][season]
    
    # Validate and update missing episodes
    if isinstance(missing_eps, list):
        # Filter out invalid episode numbers
        valid_missing = [ep for ep in missing_eps if isinstance(ep, (int, float)) and 1 <= ep <= 1000]
        season_node["missing_episodes"] = sorted(list(set(valid_missing)))  # Remove duplicates
    else:
        season_node["missing_episodes"] = []

    existing_ids = set(str(x) for x in season_node.get("mal_ids", []))
    incoming_ids = set(str(x) for x in anime_meta.get("mal_ids", []))
    if incoming_ids:
        season_node["mal_ids"] = sorted(list(existing_ids.union(incoming_ids)), key=lambda x: int(x) if x.isdigit() else 0)

    if "languages" not in season_node: season_node["languages"] = {}
    
    # Validate batches structure before saving
    validated_episodes = {}
    for batch_name, batch_files in episodes.items():
        if isinstance(batch_files, list):
            # Ensure all files have required fields
            validated_files = []
            for file_entry in batch_files:
                if isinstance(file_entry, dict) and 'file' in file_entry:
                    validated_files.append(file_entry)
            if validated_files:
                validated_episodes[batch_name] = validated_files
    
    season_node["languages"][lang] = {"batches": validated_episodes, "specials": specials if specials else {}}

async def process_season_block(meta, collected_files, index, handler):
    if not meta or not collected_files: 
        return
    
    # Validate meta data
    if not meta.get('title') or not meta.get('season'):
        print(f"⚠️ Skipping invalid meta: {meta}")
        return
    
    # 1. Use Hybrid Handler (Regex First, AI Second)
    mapping_results = handler.process_season(collected_files, meta)
    
    ep_list_raw = []
    un_list = []
    processed_file_ids = set()

    for file_obj in collected_files:
        msg_id = file_obj['file_id']
        
        # Skip duplicates
        if msg_id in processed_file_ids:
            print(f"⚠️ Skipping duplicate file_id: {msg_id}")
            continue
        processed_file_ids.add(msg_id)
        
        entry = {
            "file": msg_id, 
            "channel_id": file_obj['channel_id'],
            "name": file_obj.get('name') or "Unknown"
        }
        
        if msg_id in mapping_results:
            result = mapping_results[msg_id]
            if result.get('type') == 'episode':
                num = result.get('num')
                end_num = result.get('end_num', num)
                
                # Final validation
                if num is not None and isinstance(num, (int, float)) and 1 <= num <= 1000:
                    entry['num'] = float(num)
                    entry['end_num'] = float(end_num) if end_num is not None else float(num)
                    # Ensure start <= end
                    if entry['num'] > entry['end_num']:
                        entry['num'], entry['end_num'] = entry['end_num'], entry['num']
                    ep_list_raw.append(entry)
                else:
                    print(f"⚠️ Invalid episode number {num} for file {msg_id}, moving to uncategorized")
                    un_list.append(entry)
            else:
                un_list.append(entry)
        else:
            un_list.append(entry)

    # 2. Build Batches with validation
    final_batches, missing_eps = build_batches_with_repair(ep_list_raw, un_list)
    
    # 3. Validate batch structure
    total_batched = sum(len(batch) for name, batch in final_batches.items() if name != "batch_uncategorized")
    uncategorized_count = len(final_batches.get("batch_uncategorized", []))
    
    print(f"📦 Batching complete: {total_batched} episodes in {len([k for k in final_batches.keys() if k != 'batch_uncategorized'])} batches, "
          f"{uncategorized_count} uncategorized, {len(missing_eps)} missing episodes")
    
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