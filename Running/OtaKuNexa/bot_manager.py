import json
import asyncio
from telethon import TelegramClient
from telethon.tl import types
from telethon.tl.functions import upload

api_id = 26533694
api_hash = "36cbb9b7134615f4dd121aac7ba98ae0"
bot_token = "8482679681:AAG98ABhFJlCHfyax1gft4ribuCU7nJOn84"

channel = "@otakunexa"

# Load your JSON file
with open("anime.json", "r", encoding="utf-8") as f:
    anime_data = json.load(f)


async def main():
    async with TelegramClient("bot_session", api_id, api_hash) as client:
        await client.start(bot_token=bot_token)
        
        bot = await client.get_me()
        print(f"Bot started: {bot.first_name}")

        for series_key, series in anime_data.items():
            print(f"\n====== {series['title']} S{series['season']} ======")

            for ep_key, ep_data in series["episodes"].items():
                msg_id = ep_data["message_id"]

                try:
                    # Fetch message
                    msg = await client.get_messages(channel, ids=msg_id)

                    if not msg or not msg.document:
                        print(f"Episode {ep_data['episode']} → ❌ No document found")
                        continue

                    # Get file information
                    doc = msg.document
                    
                    # For bot accounts, you can construct the download URL like this:
                    # This uses the Bot API method
                    file_id = doc.id
                    
                    # Get the file path using GetFile method
                    try:
                        # This gets the actual file path from Telegram servers
                        file = await client(upload.GetFileRequest(
                            types.InputDocumentFileLocation(
                                id=doc.id,
                                access_hash=doc.access_hash,
                                file_reference=doc.file_reference,
                                thumb_size=""
                            ),
                            offset=0,
                            limit=1024
                        ))
                        
                        # The file path is available, but for direct download we need a different approach
                        # Let's use the simpler bot file URL format
                        direct_url = f"https://api.telegram.org/file/bot{bot_token}/documents/{file_id}"
                        
                    except Exception as e:
                        # Fallback: use basic file ID URL
                        direct_url = f"https://api.telegram.org/file/bot{bot_token}/documents/{file_id}"
                    
                    print(f"Ep {ep_data['episode']} ({ep_data['quality']}) → {direct_url}")
                    ep_data["direct_url"] = direct_url

                except Exception as e:
                    print(f"Episode {ep_data['episode']} → ❌ Error: {e}")
                    continue

    # Save updated JSON
    with open("haikyuu_with_links.json", "w", encoding="utf-8") as f:
        json.dump(anime_data, f, indent=2, ensure_ascii=False)

    print("\nAll links saved to haikyuu_with_links.json")


if __name__ == "__main__":
    asyncio.run(main())