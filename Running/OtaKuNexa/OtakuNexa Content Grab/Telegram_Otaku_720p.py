from telethon import TelegramClient, types
import re
import json
import os
import logging
from collections import defaultdict

# ---------- CONFIG ----------
api_id = 26533694
api_hash = "36cbb9b7134615f4dd121aac7ba98ae0"
channel_username = "@otakunexa"
output_json_file = "anime_data_720p_priority.json"
# ----------------------------

client = TelegramClient("session_name", api_id, api_hash)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ IMPROVED HELPERS ------------------

def get_quality_priority(quality):
    """Get priority for quality (lower number = higher priority)"""
    quality_priority = {
        "720p": 1,
        "1080p": 2, 
        "480p": 3,
        "360p": 4,
        "240p": 5
    }
    return quality_priority.get(quality, 99)

def nearest_quality(q):
    """Convert any quality to nearest standard with 720p preference"""
    if isinstance(q, str):
        q = re.sub(r"[^0-9]", "", q)
    try:
        q = int(q)
    except (ValueError, TypeError):
        return "720p"  # Default to 720p
    
    if q <= 480:
        return "480p"
    elif q <= 720:
        return "720p"  # Prefer 720p for anything close
    else:
        return "1080p"

def extract_quality(text):
    """Extract quality from text (caption or filename)"""
    if not text:
        return "720p"  # Default to 720p
    
    patterns = [
        r"quality\s*[:\-]?\s*(\d+p)", 
        r"(\d{3,4})\s*p",
        r"\[(\d+p)\]",
        r"\((\d+p)\)",
        r"\b(480p|720p|1080p)\b"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return nearest_quality(match.group(1))
    
    return "720p"  # Default to 720p

def extract_language(text):
    """Extract language from text"""
    if not text:
        return "English"
    
    text_lower = text.lower()
    lang_patterns = {
        "Hindi": [r"hindi", r"hind?", r"हिंदी"],
        "English": [r"english", r"eng?", r"eng\d?", r"sub"],
        "Japanese": [r"japanese", r"jap", r"jpn?"]
    }
    
    for lang, patterns in lang_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return lang
    
    return "English"

def extract_episode_from_text(text, current_season):
    """Extract episode number from text (caption or filename)"""
    if not text:
        return None
    
    # Remove season number references to avoid confusion
    season_patterns = [
        rf"season\s*{current_season}",
        rf"s\s*{current_season}",
        rf"\(.*{current_season}.*\)"
    ]
    
    cleaned_text = text
    for pattern in season_patterns:
        cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE)
    
    episode_patterns = [
        r"episode\s*[:\-]?\s*(\d+)",
        r"ep\s*[\.\-\:]?\s*(\d+)", 
        r"\[(\d+)\]",
        r"#(\d+)",
        r"\b(\d{1,3})(?=\s*\[|\s*\(|\.mp4|\.mkv|\.avi|$)",
        r"_(\d+)_",
        r"\s(\d+)\s"
    ]
    
    for pattern in episode_patterns:
        matches = re.findall(pattern, cleaned_text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            ep_num = int(match)
            if 1 <= ep_num <= 200:
                return str(ep_num)
    
    return None

def get_filename_from_msg(msg):
    """Extract filename from message media"""
    if not msg or not msg.media:
        return None
    
    try:
        if hasattr(msg.media, 'document') and msg.media.document:
            for attr in msg.media.document.attributes:
                if isinstance(attr, types.DocumentAttributeFilename):
                    return attr.file_name
        return "video.mp4"
    except Exception as e:
        logger.warning(f"Error getting filename: {e}")
        return None

def get_file_extension(msg):
    """Get correct file extension from message"""
    filename = get_filename_from_msg(msg)
    if filename:
        ext = os.path.splitext(filename)[1]
        if ext and len(ext) <= 5:  # Reasonable extension length
            return ext
    return ".mp4"

def get_file_unique_id(msg):
    """Get file_unique_id reliably with fallbacks"""
    if not msg or not msg.media:
        return None
    
    try:
        if hasattr(msg.media, 'document') and msg.media.document:
            doc = msg.media.document
            if hasattr(doc, 'file_unique_id'):
                return doc.file_unique_id
            elif hasattr(doc, 'id'):
                return f"doc_{doc.id}"
                
        elif hasattr(msg.media, 'video') and msg.media.video:
            video = msg.media.video
            if hasattr(video, 'file_unique_id'):
                return video.file_unique_id
            elif hasattr(video, 'id'):
                return f"vid_{video.id}"
                
    except Exception as e:
        logger.warning(f"Error getting file_unique_id: {e}")
    
    return f"msg_{msg.id}"

def extract_episode_number(msg, current_season, prev_episode=None, is_movie=False):
    """Main function to extract episode number from message"""
    if is_movie:
        return "movie"  # Special episode number for movies
    
    # Try from caption first
    if msg.message:
        episode = extract_episode_from_text(msg.message, current_season)
        if episode:
            return episode
    
    # Try from filename
    filename = get_filename_from_msg(msg)
    if filename:
        episode = extract_episode_from_text(filename, current_season)
        if episode:
            return episode
    
    # Fallback: increment previous episode
    if prev_episode and prev_episode.isdigit():
        try:
            return str(int(prev_episode) + 1)
        except ValueError:
            pass
    
    return "1"

def generate_filename(anime_title, season, episode, quality, language, extension):
    """Generate consistent filename"""
    if episode == "movie":
        return f"{anime_title}_Movie_[{quality}]_[{language}]{extension}"
    else:
        return f"{anime_title}_S{season}E{episode}_[{quality}]_[{language}]{extension}"

def filter_best_quality_episodes(episodes_dict):
    """Filter episodes to keep only the best available quality based on priority"""
    episode_groups = defaultdict(dict)
    
    # Group episodes by anime_season_episode
    for msg_id, episode_data in episodes_dict.items():
        key = f"{episode_data['title']}_{episode_data['season']}_{episode_data['episode']}"
        episode_groups[key][msg_id] = episode_data
    
    # For each episode group, keep only the best quality
    filtered_episodes = {}
    quality_stats = defaultdict(int)
    
    for episode_key, versions in episode_groups.items():
        if len(versions) == 1:
            # Only one version, keep it
            msg_id = list(versions.keys())[0]
            filtered_episodes[msg_id] = list(versions.values())[0]
            quality_stats[list(versions.values())[0]['quality']] += 1
        else:
            # Multiple versions - choose the best quality based on priority
            best_version = None
            best_priority = float('inf')
            
            for msg_id, version_data in versions.items():
                priority = get_quality_priority(version_data['quality'])
                if priority < best_priority:
                    best_priority = priority
                    best_version = (msg_id, version_data)
            
            if best_version:
                filtered_episodes[best_version[0]] = best_version[1]
                quality_stats[best_version[1]['quality']] += 1
                logger.info(f"Selected {best_version[1]['quality']} for {episode_key} "
                           f"(had {len(versions)} versions)")
    
    return filtered_episodes, quality_stats

# ------------------ MAIN PROCESSING ------------------

async def main():
    anime_data = {}
    active_anime = None
    prev_episode = None
    current_season = None

    async for msg in client.iter_messages(channel_username, reverse=True):
        text = msg.message or ""
        logger.info(f"Processing message {msg.id}: {text[:100]}...")

        # Handle MISTAKE case first
        if "</MISTAKE(START)>" in text:
            parts = text.split("</MISTAKE(START)>")
            if len(parts) == 2:
                # Process first part as END
                end_text = parts[0]
                start_match = re.search(r"Title\s*:\s*([^\n]+)", end_text, re.IGNORECASE)
                season_match = re.search(r"Season\s*:\s*([^\n]+)", end_text, re.IGNORECASE)
                if start_match and season_match:
                    title = start_match.group(1).strip()
                    season = season_match.group(1).strip().lower()
                    if season == "none":
                        season = "movie"
                    key = f"{title}_S{season}"
                    if key in anime_data:
                        logger.info(f"Ending anime due to MISTAKE: {key}")
                        active_anime = None
                        prev_episode = None

                # Process second part as START
                start_text = parts[1]
                title_match = re.search(r"Title\s*:\s*([^\n]+)", start_text, re.IGNORECASE)
                season_match = re.search(r"Season\s*:\s*([^\n]+)", start_text, re.IGNORECASE)
                handle_match = re.search(r"(@\S+)", start_text)
                
                if title_match and season_match:
                    title = title_match.group(1).strip()
                    season = season_match.group(1).strip().lower()
                    if season == "none":
                        season = "movie"
                    handle = handle_match.group(1).strip() if handle_match else ""
                    key = f"{title}_S{season}"
                    
                    if key not in anime_data:
                        anime_data[key] = {
                            "title": title,
                            "season": season,
                            "is_movie": "_movie" in handle.lower() or season == "movie",
                            "handle": handle,
                            "episodes": {}
                        }
                    
                    active_anime = key
                    current_season = season
                    prev_episode = None
                    logger.info(f"Started new anime from MISTAKE: {key}")
                continue

        # Handle ANIME_START
        if "<ANIME_START>" in text:
            title_match = re.search(r"Title\s*:\s*([^\n]+)", text, re.IGNORECASE)
            season_match = re.search(r"Season\s*:\s*([^\n]+)", text, re.IGNORECASE)
            handle_match = re.search(r"(@\S+)", text)
            
            if title_match and season_match:
                title = title_match.group(1).strip()
                season = season_match.group(1).strip().lower()
                if season == "none":
                    season = "movie"
                handle = handle_match.group(1).strip() if handle_match else ""
                key = f"{title}_S{season}"
                
                if key not in anime_data:
                    anime_data[key] = {
                        "title": title,
                        "season": season,
                        "is_movie": "_movie" in handle.lower() or season == "movie",
                        "handle": handle,
                        "episodes": {}
                    }
                
                active_anime = key
                current_season = season
                prev_episode = None
                logger.info(f"Started new anime: {key}")
            continue

        # Handle ANIME_END
        if "<ANIME_END>" in text:
            title_match = re.search(r"Title\s*:\s*([^\n]+)", text, re.IGNORECASE)
            season_match = re.search(r"Season\s*:\s*([^\n]+)", text, re.IGNORECASE)
            
            if title_match and season_match:
                title = title_match.group(1).strip()
                season = season_match.group(1).strip().lower()
                if season == "none":
                    season = "movie"
                key = f"{title}_S{season}"
                
                if key in anime_data:
                    logger.info(f"Ending anime: {key}")
                    active_anime = None
                    prev_episode = None
                    current_season = None
            continue

        # Process Media Messages
        if active_anime and msg.media:
            is_media = False
            file_unique_id = None
            
            try:
                if (hasattr(msg.media, 'document') and msg.media.document) or \
                   (hasattr(msg.media, 'video') and msg.media.video):
                    is_media = True
                    file_unique_id = get_file_unique_id(msg)
            except Exception as e:
                logger.warning(f"Error checking media for message {msg.id}: {e}")
            
            if is_media:
                # Extract episode number
                is_movie = anime_data[active_anime]["is_movie"]
                episode_number = extract_episode_number(msg, current_season, prev_episode, is_movie)
                prev_episode = episode_number
                
                # Extract quality and language
                quality = extract_quality(msg.message or "")
                language = extract_language(msg.message or "")
                
                # Get file extension
                extension = get_file_extension(msg)
                filename = generate_filename(
                    anime_data[active_anime]["title"],
                    anime_data[active_anime]["season"],
                    episode_number,
                    quality,
                    language,
                    extension
                )
                
                # Store episode data
                anime_data[active_anime]["episodes"][str(msg.id)] = {
                    "message_id": msg.id,
                    "file_unique_id": file_unique_id,
                    "title": anime_data[active_anime]['title'],
                    "season": anime_data[active_anime]['season'],
                    "episode": episode_number,
                    "quality": quality,
                    "language": language,
                    "filename": filename,
                    "caption": msg.message or ""
                }
                
                logger.info(f"Added episode: {filename}")

    # FILTER EPISODES TO KEEP ONLY BEST QUALITY
    logger.info("Filtering episodes to keep only best quality...")
    total_episodes_before = 0
    total_episodes_after = 0
    overall_quality_stats = defaultdict(int)
    
    for anime_key in anime_data:
        episodes = anime_data[anime_key]["episodes"]
        total_episodes_before += len(episodes)
        
        filtered_episodes, quality_stats = filter_best_quality_episodes(episodes)
        anime_data[anime_key]["episodes"] = filtered_episodes
        total_episodes_after += len(filtered_episodes)
        
        # Accumulate quality stats
        for quality, count in quality_stats.items():
            overall_quality_stats[quality] += count
        
        logger.info(f"{anime_key}: {len(episodes)} -> {len(filtered_episodes)} episodes")

    # Save JSON
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(anime_data, f, ensure_ascii=False, indent=2)
    
    # Print summary
    total_anime = len(anime_data)
    logger.info("=" * 50)
    logger.info("PROCESSING COMPLETE!")
    logger.info(f"Total anime: {total_anime}")
    logger.info(f"Total episodes before filtering: {total_episodes_before}")
    logger.info(f"Total episodes after filtering: {total_episodes_after}")
    logger.info(f"Duplicates removed: {total_episodes_before - total_episodes_after}")
    logger.info("Quality distribution:")
    for quality in ["720p", "1080p", "480p", "360p", "240p"]:
        count = overall_quality_stats.get(quality, 0)
        percentage = (count / total_episodes_after * 100) if total_episodes_after > 0 else 0
        logger.info(f"  {quality}: {count} episodes ({percentage:.1f}%)")
    logger.info("=" * 50)
    
    print(f"JSON saved to {output_json_file}")

# ------------------ RUN ------------------
if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())