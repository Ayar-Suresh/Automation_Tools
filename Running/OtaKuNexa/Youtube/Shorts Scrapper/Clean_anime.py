import json

# Input and output files
input_file = r"C:\Users\Ahir\Desktop\Shorts Scrapper\Playlist\youtube_playlists_batches.json"
cleaned_file = r"C:\Users\Ahir\Desktop\playlists_cleaned.json"
limited_file = r"C:\Users\Ahir\Desktop\playlists_limited_time.json"

# Load JSON batches
with open(input_file, "r", encoding="utf-8") as f:
    batches = json.load(f)

cleaned_batches = []
limited_batches = []

for batch in batches:
    # Copy batch-level structure
    cleaned_batch = {k: batch[k] for k in batch if k != "items"}
    limited_batch = {k: batch[k] for k in batch if k != "items"}

    cleaned_items = []
    limited_items = []

    for playlist in batch.get("items", []):
        title = playlist["snippet"]["title"]

        # If it's a limited-time playlist, move it to limited_items
        if "(Limited time only)" in title:
            limited_items.append(playlist)
            continue

        # Keep only essential fields in snippet
        snippet = {
            "title": title,
            "channelId": playlist["snippet"].get("channelId"),
            "thumbnails": {}
        }

        thumbnails = playlist["snippet"].get("thumbnails", {})
        if "medium" in thumbnails:
            snippet["thumbnails"]["medium"] = thumbnails["medium"]
        if "high" in thumbnails:
            snippet["thumbnails"]["high"] = thumbnails["high"]

        # Rebuild playlist object
        cleaned_playlist = {
            "id": playlist.get("id"),
            "snippet": snippet,
            "contentDetails": playlist.get("contentDetails", {})
        }

        cleaned_items.append(cleaned_playlist)

    # Assign filtered items to batch
    cleaned_batch["items"] = cleaned_items
    limited_batch["items"] = limited_items

    cleaned_batches.append(cleaned_batch)
    if limited_items:
        limited_batches.append(limited_batch)

# Save cleaned playlists JSON
with open(cleaned_file, "w", encoding="utf-8") as f:
    json.dump(cleaned_batches, f, indent=4, ensure_ascii=False)

# Save limited-time playlists JSON
with open(limited_file, "w", encoding="utf-8") as f:
    json.dump(limited_batches, f, indent=4, ensure_ascii=False)

print(f"✅ Cleaned playlists saved to: {cleaned_file}")
print(f"✅ Limited-time playlists saved to: {limited_file}")

