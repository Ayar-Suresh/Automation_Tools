
import asyncio
import os
import json
import re
from telethon import TelegramClient
from groq import Groq

# ================= CONFIGURATION =================
API_ID = 26533694
API_HASH = "36cbb9b7134615f4dd121aac7ba98ae0"
GROQ_API_KEY = "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"

SOURCE_CHANNEL = -1001994105717
DESTINATION_CHANNEL = -1003628341173
SESSION_NAME = 'OtakuNexa_Smart_Session'

# ================= AI & HELPER FUNCTIONS =================
# We use the 70B model. It is much smarter at understanding context.
groq_client = Groq(api_key=GROQ_API_KEY)
MODEL_NAME = "llama-3.3-70b-versatile" 

def normalize_name(name):
    """
    Standardizes names to ensure 'Twilight Out Of Focus' matches 'Twilight Out of Focus'.
    """
    if not name or name == "Unknown": return "unknown"
    # Lowercase and remove all non-alphanumeric characters
    return re.sub(r'[^a-z0-9]', '', name.lower())

def analyze_text_smart(caption, filename):
    """
    Uses the 70B model to intelligently parse the message.
    """
    # clear indication of what is what
    user_content = f"""
    [SOURCE DATA]
    CAPTION: "{caption}"
    FILENAME: "{filename}"
    """

    system_prompt = """
    You are an expert Anime Archivist. Your job is to identify the Anime Name, Episode, and Quality from the provided [SOURCE DATA].

    CRITICAL RULES:
    1. **PRIORITY:** Trust the CAPTION 100% more than the FILENAME. 
       - If the Caption says "One Piece - 1000", but the Filename says "hjd83d.mkv", USE THE CAPTION.
       - Only look at the Filename if the Caption is missing or useless.
    
    2. **INTELLIGENCE:** - Ignore garbage names (e.g., "xjsksks", "28374").
       - If you see "Twilight Out of Focus", that is the name.
       - If you see "Pick_Me_S", standard english is "Pick Me".
       - If the caption is just a link or spam, ignore it and return "Unknown".

    3. **QUALITY PARSING:**
       - "720p", "720", "HD", "1280x720" -> Output 720.
       - "1080p", "FHD", "1080" -> Output 1080.
       - "480p", "SD", "480" -> Output 480.
       - If quality is completely missing, default to 480.

    OUTPUT FORMAT:
    You must return a single JSON object. Do not explain anything.
    {
        "name": "Standardized Anime Name (Title Case)",
        "episode": <integer_number>,
        "quality": <integer_number>
    }
    """

    try:
        completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            model=MODEL_NAME,
            temperature=0.1, # Keep it strict
            max_tokens=100
        )
        
        # Clean the response to ensure it's pure JSON
        raw_response = completion.choices[0].message.content
        json_str = raw_response.replace("```json", "").replace("```", "").strip()
        
        return json.loads(json_str)

    except Exception as e:
        # print(f"AI Error: {e}")
        return None

# ================= MAIN LOGIC =================

async def main():
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        print(f"Connected as: {(await client.get_me()).first_name}")
        print(f"Using Brain: {MODEL_NAME} (Smarter)")

        # Structure: { "normalized_id": { "display_name": "Name", "eps": { 1: {720: msg_id}, ... } } }
        inventory = {}

        print("\n--- PHASE 1: Scanning & Indexing ---")
        
        # We scan ALL messages first to build the perfect list
        async for message in client.iter_messages(SOURCE_CHANNEL, reverse=True):
            if message.file:
                caption = message.text or ""
                filename = message.file.name or ""
                
                # Skip messages with absolutely no info
                if len(caption) < 2 and len(filename) < 2:
                    continue

                # VISUAL LOG: Show user what we are scanning
                print(f"Scanning Msg {message.id}...", end="\r")

                # AI ANALYSIS
                data = analyze_text_smart(caption, filename)

                if data and data.get('name') and data['name'] != "Unknown":
                    # Extract Data
                    real_name = data['name']
                    try:
                        ep_num = int(data['episode'])
                    except:
                        continue # Skip if no valid episode number

                    qual = int(data.get('quality', 480))

                    # Normalize Quality (Fix dumb mistakes like 700p)
                    if 680 <= qual <= 790: qual = 720
                    elif 1000 <= qual <= 1920: qual = 1080
                    elif qual < 680: qual = 480

                    # Create a "Key" to group similar names
                    norm_key = normalize_name(real_name)

                    # Add to Inventory
                    if norm_key not in inventory:
                        inventory[norm_key] = {"display_name": real_name, "eps": {}}
                    
                    if ep_num not in inventory[norm_key]["eps"]:
                        inventory[norm_key]["eps"][ep_num] = {}
                    
                    # Store this message for this specific quality
                    inventory[norm_key]["eps"][ep_num][qual] = message.id

        print("\n\n--- PHASE 2: Intelligent Forwarding ---")
        
        for norm_key, anime_data in inventory.items():
            display_name = anime_data['display_name']
            episodes = anime_data['eps']
            
            print(f"\n📺 Processing: {display_name}")
            
            # Sort episodes naturally (1, 2, 3...)
            sorted_episodes = sorted(episodes.keys())

            if not sorted_episodes:
                continue

            for ep in sorted_episodes:
                available_qualities = episodes[ep] # e.g. {720: 1234, 480: 5678}
                
                # THE DECISION MAKER
                msg_to_send = None
                status = ""

                if 720 in available_qualities:
                    msg_to_send = available_qualities[720]
                    status = "720p (Preferred)"
                elif 1080 in available_qualities:
                    msg_to_send = available_qualities[1080]
                    status = "1080p (Backup)"
                elif 480 in available_qualities:
                    msg_to_send = available_qualities[480]
                    status = "480p (Low Res)"
                else:
                    # If we have a weird quality (like 540p), just take the first one
                    msg_to_send = list(available_qualities.values())[0]
                    status = "Best Available"

                # Action
                if msg_to_send:
                    print(f"   -> Forwarding Ep {ep} [{status}]")
                    try:
                        await client.forward_messages(DESTINATION_CHANNEL, msg_to_send, SOURCE_CHANNEL)
                        await asyncio.sleep(2) # Prevent FloodWait
                    except Exception as e:
                        print(f"      [Error] {e}")

        print("\n--- JOB COMPLETE ---")

if __name__ == '__main__':
    asyncio.run(main())