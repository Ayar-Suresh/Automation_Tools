import json
import os
import base64
import asyncio
from telethon import TelegramClient, events

# ================= CONFIGURATION =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
BOT_TOKEN = "8482679681:AAG98ABhFJlCHfyax1gft4ribuCU7nJOn84" 

# Fallback Channels (Used if JSON doesn't specify channel_id)
SOURCE_CHANNELS = [
    -1003175788400,
    -1003498912074
]

JSON_FILE = "anime_index.json"
AUTO_DELETE_SECONDS = 3600 # 1 Hour

# ================= DATA LOADING =================
def load_index():
    if not os.path.exists(JSON_FILE):
        print("❌ JSON file not found!")
        return {}
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading JSON: {e}")
        return {}

ANIME_DATA = load_index()

# ================= UTILS: SMART SEARCH (AGGREGATED) =================
def find_batch_in_season(season_data, batch_key):
    """
    Robust Search:
    1. Direct Batch Match: Looks for exact key (e.g., 'batch1') anywhere.
    2. Special Aggregation: Collects ALL specials from ALL languages to ensure we find 'Special_N'.
    """
    
    # --- Helper: Find specific key recursively ---
    def search_key_recursive(data, target_key):
        if isinstance(data, dict):
            if target_key in data: return data[target_key]
            for k, v in data.items():
                if isinstance(v, dict) and k not in ["mal_ids", "missing_episodes"]:
                    res = search_key_recursive(v, target_key)
                    if res: return res
        return None

    # --- Helper: Collect ALL specials from everywhere ---
    def collect_all_specials(data):
        specials_list = []
        if isinstance(data, dict):
            # If we found a "specials" container, add its contents
            if "specials" in data and isinstance(data["specials"], dict):
                # SPECIAL FIX: Extract the values (file objects) from the specials dictionary
                for sp_name, sp_file in data["specials"].items():
                    if isinstance(sp_file, dict):
                        # Add the file object with its name
                        sp_file_copy = sp_file.copy()
                        if 'name' not in sp_file_copy:
                            sp_file_copy['name'] = sp_name
                        specials_list.append(sp_file_copy)
                    else:
                        # If it's not a dict, wrap it
                        specials_list.append({"file": sp_file, "name": sp_name})
            
            # Continue searching deeper (e.g. inside languages)
            for k, v in data.items():
                if isinstance(v, dict) and k not in ["mal_ids", "missing_episodes"]:
                    specials_list.extend(collect_all_specials(v))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            specials_list.extend(collect_all_specials(item))
        return specials_list

    # -------------------------------------------
    # STRATEGY 1: Exact Key Match (Batches)
    # -------------------------------------------
    found_data = search_key_recursive(season_data, batch_key)

    # -------------------------------------------
    # STRATEGY 2: Special Index Mapping (Aggregated)
    # -------------------------------------------
    if not found_data and batch_key.lower().startswith("special_"):
        print(f"🔍 Looking for special: {batch_key}")
        try:
            # Parse Index: "Special_1" -> index 0
            # Handle "Special 1", "Special_01", etc.
            clean_key = batch_key.lower().replace("special", "").replace("_", "").replace(" ", "").strip()
            idx = int(clean_key) - 1
            
            # 🚀 CORE FIX: Gather ALL specials from the entire season object
            all_specials = collect_all_specials(season_data)
            
            print(f"DEBUG: Raw specials collected: {all_specials}")
            
            # Sort them by name to ensure consistent order (Special 1, Special 2...)
            all_specials.sort(key=lambda x: x.get('name', ''))
            
            print(f"DEBUG: Found {len(all_specials)} specials after sorting: {[s.get('name', '') for s in all_specials]}")
            
            if 0 <= idx < len(all_specials):
                found_data = [all_specials[idx]]  # Wrap in list to match batch format
                print(f"✅ Mapped '{batch_key}' -> '{found_data[0].get('name')}'")
            else:
                print(f"DEBUG: Index {idx} out of bounds. Found {len(all_specials)} specials.")
                return None

        except Exception as e:
            print(f"⚠️ Special mapping failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    # -------------------------------------------
    # STRATEGY 3: Direct specials access
    # -------------------------------------------
    if not found_data and "languages" in season_data:
        # Try to find specials directly in languages
        for lang, lang_data in season_data["languages"].items():
            if "specials" in lang_data and batch_key in lang_data["specials"]:
                found_data = [lang_data["specials"][batch_key]]
                print(f"✅ Direct found '{batch_key}' in {lang}")
                break
            elif "specials" in lang_data and batch_key.lower().startswith("special_"):
                # Try Special_1, Special_2 format
                try:
                    clean_key = batch_key.lower().replace("special", "").replace("_", "").replace(" ", "").strip()
                    idx = int(clean_key) - 1
                    specials_list = list(lang_data["specials"].values())
                    specials_list.sort(key=lambda x: x.get('name', ''))
                    
                    if 0 <= idx < len(specials_list):
                        found_data = [specials_list[idx]]
                        print(f"✅ Direct indexed '{batch_key}' -> '{found_data[0].get('name')}'")
                        break
                except:
                    pass

    # -------------------------------------------
    # Normalize Result to List
    # -------------------------------------------
    if found_data:
        if isinstance(found_data, list): return found_data
        elif isinstance(found_data, dict): return [found_data]
            
    return None

# ================= BACKGROUND TASK =================
async def schedule_delete(client, chat_id, message_ids):
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    try:
        await client.delete_messages(chat_id, message_ids)
    except Exception as e:
        print(f"Failed to auto-delete for {chat_id}: {e}")

# ================= BOT SETUP =================
client = TelegramClient("secure_delivery_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@client.on(events.NewMessage(pattern=r"/start (.+)"))
async def batch_handler(event):
    payload = event.pattern_match.group(1).strip()
    
    try:
        # --- DECODE PAYLOAD ---
        decoded_bytes = base64.urlsafe_b64decode(payload + '===')
        decoded_str = decoded_bytes.decode('utf-8')
        
        parts = decoded_str.split('|')
        if len(parts) != 3:
            await event.reply("❌ **Invalid Access Token.**")
            return
            
        anime_title = parts[0]
        season_num = parts[1]
        batch_key = parts[2] 
        
        print(f"🔍 Request: {anime_title} | Season {season_num} | Batch: {batch_key}")
        
        # --- FETCH DATA ---
        try:
            # Debug: Show what keys exist
            if anime_title not in ANIME_DATA:
                await event.reply(f"⚠️ **Anime not found:** {anime_title}")
                return
                
            print(f"DEBUG: Anime in data: {anime_title in ANIME_DATA}")
            if anime_title in ANIME_DATA:
                print(f"DEBUG: Seasons available: {list(ANIME_DATA[anime_title]['seasons'].keys())}")
                
            season_data = ANIME_DATA[anime_title]["seasons"][season_num]
            
            # Debug: Show structure of season data
            print(f"DEBUG: Season data keys: {list(season_data.keys())}")
            if "languages" in season_data:
                print(f"DEBUG: Languages: {list(season_data['languages'].keys())}")
                for lang in season_data['languages']:
                    if 'specials' in season_data['languages'][lang]:
                        specials = season_data['languages'][lang]['specials']
                        print(f"DEBUG: {lang} specials keys: {list(specials.keys())}")
                        print(f"DEBUG: {lang} specials values: {specials}")
            
            print(f"🔎 Searching for '{batch_key}'...")
            batch_files = find_batch_in_season(season_data, batch_key)
            
            print(f"DEBUG: Found batch files: {batch_files}")
            
            if not batch_files:
                print(f"DEBUG: '{batch_key}' not found in {anime_title} S{season_num}")
                await event.reply(f"⚠️ **Content Unavailable:**\nCould not find **{batch_key}** for {anime_title} Season {season_num}.\nTry refreshing the App.")
                return
                
        except KeyError as e:
            print(f"KeyError: {e}")
            import traceback
            traceback.print_exc()
            await event.reply(f"⚠️ **Content Unavailable:**\nCould not find **{anime_title}**.\nTry refreshing the App.")
            return

        # --- WARNING MESSAGE ---
        # Get the actual name from the first file if available
        if batch_files and len(batch_files) > 0 and 'name' in batch_files[0]:
            display_name = batch_files[0]['name']
        else:
            display_name = batch_key.replace('_', ' ').replace('batch', 'Batch ').title()
        
        warning_text = (
            f"🎬 **{anime_title}** (Season {season_num})\n"
            f"📂 **{display_name}**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🇬🇧 **IMPORTANT:** Files auto-delete in **1 Hour**.\n"
            "Save them immediately!\n\n"
            "🇮🇳 **महत्वपूर्ण:** फाइलें **1 घंटे** में डिलीट हो जाएंगी।\n"
            "तुरंत सेव करें!\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 *Processing...*"
        )

        status_msg = await event.reply(warning_text)

        # --- SENDING LOGIC ---
        sent_messages = []
        
        for item in batch_files:
            if not isinstance(item, dict): 
                print(f"DEBUG: Skipping non-dict item: {item}")
                continue
            msg_id = item.get('file')
            if not msg_id: 
                print(f"DEBUG: No file ID in item: {item}")
                continue

            # Smart Channel ID Selection
            target_channels = [item['channel_id']] if 'channel_id' in item else SOURCE_CHANNELS
            
            file_sent = False
            for channel_id in target_channels:
                try:
                    print(f"DEBUG: Forwarding msg_id {msg_id} from channel {channel_id}")
                    msgs = await client.forward_messages(
                        event.chat_id, 
                        messages=msg_id, 
                        from_peer=channel_id,
                        drop_author=True 
                    )
                    if msgs:
                        sent_messages.append(msgs)
                        file_sent = True
                        print(f"DEBUG: Successfully forwarded message {msg_id}")
                        break 
                except Exception as e:
                    print(f"DEBUG: Failed to forward from channel {channel_id}: {e}")
                    continue 
            
            if not file_sent:
                print(f"❌ Failed to fetch Message {msg_id}")

        if sent_messages:
            ids_to_delete = [m.id for m in sent_messages]
            ids_to_delete.append(status_msg.id)
            asyncio.create_task(schedule_delete(client, event.chat_id, ids_to_delete))
        else:
            await event.reply("❌ **System Error:** Files have been deleted from the source channel.")

    except Exception as e:
        await event.reply("❌ **Link Invalid.**")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

@client.on(events.NewMessage(pattern=r"^/start$"))
async def block_direct_access(event):
    await event.reply("⛔ **Access Denied.** Use the App.")

print("🔒 Secure Delivery Bot is Running...")
client.run_until_disconnected()