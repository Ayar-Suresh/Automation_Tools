import os
import json
import time

# ==============================================================================
# ⚙️ CONFIGURATION (Must match your Dart Code)
# ==============================================================================
REPO_METADATA = "daily-kaam-logs"       # For Home Screen / Updates
PATH_METADATA = "work/sys_patch.json"

REPO_INDEX    = "project-store-v9"      # For Anime Downloads
PATH_INDEX    = "assets/texture_map.json"

# ==============================================================================
# 🧮 MATH LOGIC (The Core of Ghost Protocol)
# ==============================================================================
def get_ghost_identity(version):
    """
    Replicates the EXACT logic from AnimeDownloadService.dart
    """
    version = int(version)
    
    # 1. Num1 Logic
    num1 = 0 if version == 1 else version

    # 2. Num2 Logic
    num2 = 0 if version % 2 == 0 else (version - 1)

    # 3. Suffix Logic
    v = version - 1
    suffix = 6814 + (v * 19) + (v * v * 7)

    return f"OtexSever{num1}LogK{num2}TNENGQ{suffix}"

# ==============================================================================
# 🛠️ HELPER FUNCTIONS
# ==============================================================================
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    print("\033[95m" + "="*70)
    print(" 🤖  OTAKU NEXA: INFRASTRUCTURE COMMAND CENTER  🤖")
    print("="*70 + "\033[0m")
    print(" This tool ensures your App and Server stay perfectly synced.")
    print("-" * 70 + "\n")

def print_copy_block(title, content):
    print(f"\n\033[96m👇 {title} (COPY BELOW) 👇\033[0m")
    print("\033[90m" + "-"*70)
    print(content)
    print("-" * 70 + "\033[0m")

# ==============================================================================
# 1️⃣ FEATURE: CONFIG JSON GENERATOR (Updates & Bots)
# ==============================================================================
def flow_generate_config():
    print_header()
    print("\n🔵  MODE: CONFIGURATION UPDATE GENERATOR")
    print("    Generate the JSON to Paste into 'sys_patch.json' or 'anime_index.json'\n")

    # 1. Bot Configuration
    print("🤖  BOT SETTINGS:")
    change_bot = input("    Do you want to change the Telegram Bot? (y/n): ").lower()
    bot_name = None
    if change_bot == 'y':
        bot_name = input("    👉 Enter NEW Bot Username (no @): ").strip()
    
    # 2. App Update Configuration
    print("\n📲  APP UPDATE SETTINGS:")
    push_update = input("    Do you want to push an App Update? (y/n): ").lower()
    
    update_data = None
    if push_update == 'y':
        version = input("    👉 Latest Version (e.g. 1.0.2): ").strip()
        force = input("    👉 Force Update? (y/n): ").lower() == 'y'
        url = input("    👉 Download URL (APK Link): ").strip()
        print("    👉 Enter Changelog (Type 'END' on a new line to finish):")
        lines = []
        while True:
            line = input()
            if line == 'END': break
            lines.append(line)
        changelog = "\n".join(lines)
        
        update_data = {
            "latest_version": version,
            "force_update": force,
            "download_url": url,
            "changelog": changelog
        }

    # 3. Construct JSON
    config = {}
    if bot_name:
        config["override_bot"] = bot_name
    
    if update_data:
        config["app_update"] = update_data

    # Wrap in the main structure
    final_json = {
        "config": config,
        "recent_added_category": [
            {"mal_id": 9999, "title": "Example Anime (Replace with Data)..."}
        ]
    }

    json_str = json.dumps(final_json, indent=2)
    
    print_copy_block("JSON FOR GITHUB (sys_patch.json or anime_index.json)", json_str)
    print("\n✅ Instructions: Paste this entire block into your active GitHub repo file.")
    input("\nPress Enter to return...")

# ==============================================================================
# 2️⃣ FEATURE: GHOST IDENTITY CALCULATOR
# ==============================================================================
def flow_ghost_manager():
    print_header()
    print("\n🟣  MODE: SERVER INFRASTRUCTURE MANAGER")
    print("    Calculate usernames and file paths for new Ghost Servers.\n")

    try:
        v_input = input("👉 Enter Version Number (e.g. 10, 60, 110): ").strip()
        version = int(v_input)
    except:
        print("❌ Invalid Number")
        time.sleep(1)
        return

    username = get_ghost_identity(version)
    bot_def = f"@{username}_bot"

    print("\n" + "="*60)
    print(f"👻  IDENTITY FOR VERSION: {version}")
    print("="*60)
    print(f"👤  GITHUB USERNAME:   \033[92m{username}\033[0m")
    print(f"🤖  SUGGESTED BOT:     \033[93m{bot_def}\033[0m")
    print("-" * 60)

    print("\n📂  REPO 1: HOME SCREEN & UPDATES (sys_patch.json)")
    print(f"    • Repo Name:   {REPO_METADATA}")
    print(f"    • File Path:   {PATH_METADATA}")
    print(f"    • RAW URL:     \033[94mhttps://raw.githubusercontent.com/{username}/{REPO_METADATA}/main/{PATH_METADATA}\033[0m")

    print("\n📂  REPO 2: ANIME DOWNLOADS (texture_map.json)")
    print(f"    • Repo Name:   {REPO_INDEX}")
    print(f"    • File Path:   {PATH_INDEX}")
    print(f"    • RAW URL:     \033[94mhttps://raw.githubusercontent.com/{username}/{REPO_INDEX}/main/{PATH_INDEX}\033[0m")

    print("\n" + "="*60)
    input("Press Enter to return...")

# ==============================================================================
# 3️⃣ FEATURE: LANE STRATEGY VIEWER
# ==============================================================================
def flow_lane_strategy():
    print_header()
    print("\n🛣️   MODE: TRAFFIC LANE STRATEGY")
    print("    See which versions belong to which User Lane.\n")

    print("Which Lane to check?")
    print(" [1] Lane 1 (10-19 -> 60-69...)")
    print(" [2] Lane 2 (20-29 -> 70-79...)")
    print(" [3] Lane 3 (30-39 -> 80-89...)")
    print(" [4] Lane 4 (40-49 -> 90-99...)")
    print(" [5] Lane 5 (50-59 -> 100-109...)")
    
    try:
        lane = int(input("\n👉 Select Lane (1-5): "))
        if lane < 1 or lane > 5: return
    except: return

    base_start = lane * 10
    
    print(f"\n📊 Strategy for Lane {lane}:\n")
    print(f"{'TIER':<10} | {'RANGE':<15} | {'SAMPLE USERNAME (First in Batch)'}")
    print("-" * 70)

    for tier in range(5): # Show first 5 tiers
        current_base = base_start + (tier * 50)
        end_base = current_base + 9
        sample_user = get_ghost_identity(current_base)
        print(f"Tier {tier:<5} | V{current_base} - V{end_base:<5} | {sample_user}")

    print("-" * 70)
    input("\nPress Enter to return...")

# ==============================================================================
# 🚀 MAIN LOOP
# ==============================================================================
def main():
    while True:
        print_header()
        print(" [1] 📝 Generate Config JSON (Bot Change / App Update)")
        print(" [2] 👻 Ghost Identity Calculator (Get Server Details)")
        print(" [3] 🛣️  View Lane Strategy")
        print(" [4] ❌ Exit")

        choice = input("\n👉 Select Option: ")

        if choice == '1':
            flow_generate_config()
        elif choice == '2':
            flow_ghost_manager()
        elif choice == '3':
            flow_lane_strategy()
        elif choice == '4':
            print("Sayonara! 👋")
            break

if __name__ == "__main__":
    main()