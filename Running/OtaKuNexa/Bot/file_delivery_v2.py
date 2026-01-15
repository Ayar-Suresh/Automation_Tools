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

# ================= UTILS: SMART SEARCH (FIXED) =================
def find_batch_in_season(season_data, batch_key):
    """
    Searches for a key in:
    1. Legacy Batches
    2. Legacy Specials
    3. Language Batches
    4. Language Specials
    
    Returns a LIST of files.
    """
    found_data = None

    # --- 1. Check Legacy Structure (Direct) ---
    if "batches" in season_data and batch_key in season_data["batches"]:
        found_data = season_data["batches"][batch_key]
    
    elif "specials" in season_data and batch_key in season_data["specials"]:
        found_data = season_data["specials"][batch_key]

    # --- 2. Check New Structure (Languages) ---
    elif "languages" in season_data:
        for lang, lang_data in season_data["languages"].items():
            # Check Batches inside Language
            if "batches" in lang_data and batch_key in lang_data["batches"]:
                found_data = lang_data["batches"][batch_key]
                break
            
            # Check Specials inside Language
            if "specials" in lang_data and batch_key in lang_data["specials"]:
                found_data = lang_data["specials"][batch_key]
                break
    
    # --- 3. Normalize Result ---
    if found_data:
        # If it's a single dictionary (Special), wrap it in a list
        if isinstance(found_data, dict):
            return [found_data]
        # If it's already a list (Batch), return it
        elif isinstance(found_data, list):
            return found_data
            
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
        batch_key = parts[2] # This could be "batch1", "batch_uncategorized", or "Special_1"
        
        # --- FETCH DATA (SMART LOOKUP) ---
        try:
            season_data = ANIME_DATA[anime_title]["seasons"][season_num]
            batch_files = find_batch_in_season(season_data, batch_key)
            
            if not batch_files:
                # Debugging info
                print(f"DEBUG: Failed to find key '{batch_key}' in {anime_title} S{season_num}")
                raise KeyError("Content not found")
                
        except KeyError:
            await event.reply(f"⚠️ **Content Unavailable:**\nCould not find requested content for **{anime_title}**.\nTry refreshing the App.")
            return

        # --- WARNING MESSAGE ---
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
            msg_id = item['file']
            # Smart Channel ID Selection
            target_channels = [item['channel_id']] if 'channel_id' in item else SOURCE_CHANNELS
            
            file_sent = False
            for channel_id in target_channels:
                try:
                    msgs = await client.forward_messages(
                        event.chat_id, 
                        messages=msg_id, 
                        from_peer=channel_id,
                        drop_author=True 
                    )
                    if msgs:
                        sent_messages.append(msgs)
                        file_sent = True
                        break 
                except Exception:
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

@client.on(events.NewMessage(pattern=r"^/start$"))
async def block_direct_access(event):
    await event.reply("⛔ **Access Denied.** Use the App.")

print("🔒 Secure Delivery Bot is Running...")
client.run_until_disconnected()