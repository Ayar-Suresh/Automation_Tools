import time

def clear_screen():
    print("\033[H\033[J", end="")

def print_header():
    print("\n" + "="*70)
    print(" 🤖  OTAKU NEXA: INFRASTRUCTURE MANAGER  🤖")
    print("="*70)
    print(" This tool ensures your App and Server stay perfectly synced.")
    print("-" * 70 + "\n")

def get_ghost_identity(version):
    """
    Replicates the EXACT logic from AnimeDownloadService.dart
    """
    # 1. Num1 Logic: If V1 -> 0, Else -> Version
    if version == 1:
        num1 = 0
    else:
        num1 = version

    # 2. Num2 Logic: If Even -> 0, If Odd -> Version - 1
    if version % 2 == 0:
        num2 = 0
    else:
        num2 = version - 1

    # 3. Suffix Logic: Quadratic Formula
    # Formula: 6814 + (v * 19) + (v^2 * 7)
    v = version - 1
    suffix = 6814 + (v * 19) + (v * v * 7)

    return f"OtexSever{num1}LogK{num2}TNENGQ{suffix}"
  

# ==============================================================================
# 1️⃣ FEATURE: BOT REPLACEMENT HELPER
# ==============================================================================
def flow_change_bot_name():
    print("\n🔵  MODE: EMERGENCY BOT REPLACEMENT")
    print("    Use this when your GitHub Account is SAFE, but the BOT is BANNED.\n")
    
    new_bot_name = input("👉 Enter the NEW Bot Username (without @): ").strip()
    
    if not new_bot_name:
        print("❌ Error: Name cannot be empty.")
        return

    print("\n" + "="*70)
    print(f"✅  STEP 1: COPY THIS CODE BLOCK")
    print("="*70)
    print("Insert this at the very top of your JSON file:")
    print("-" * 30)
    
    json_snippet = f'''{{
  "config": {{
    "override_bot": "{new_bot_name}"
  }},
  "Haikyuu": {{ ... (Rest of your anime data) ... }}
}}'''
    print(json_snippet)
    print("-" * 30)

    print("\n" + "="*70)
    print(f"✅  STEP 2: UPDATE THESE FILES ON GITHUB")
    print("="*70)
    print("You must edit the JSON files in your currently active accounts.")
    print("\n1️⃣  PRIMARY / REMOTE CONFIG (If active):")
    print("    File: anime_index/anime_index.json")
    print("\n2️⃣  GHOST LAYER (If active):")
    print("    Repo: project-store-v9")
    print("    File: assets/texture_map.json")
    print("\n💡 NOTE: The App will detect this change and switch bots instantly.")
    print("="*70 + "\n")

# ==============================================================================
# 2️⃣ FEATURE: GITHUB VERSION GENERATOR
# ==============================================================================
def flow_change_github_account():
    print("\n🟣  MODE: NEW GHOST IDENTITY GENERATOR")
    print("    Use this when the previous GitHub Account is BANNED.\n")
    
    try:
        version_input = input("👉 Enter the Version Number you want to create (e.g. 1, 2, 3): ")
        version = int(version_input)
    except ValueError:
        print("❌ Error: Please enter a valid number.")
        return

    username = get_ghost_identity(version)
    
    print("\n" + "="*70)
    print(f"👻  GENERATING DETAILS FOR VERSION {version}")
    print("="*70)
    print(f"👤  GITHUB USERNAME:   {username}")
    print(f"🤖  DEFAULT BOT NAME:  @{username}_bot")
    print("-" * 70)
    
    print("\n📂  PART A: REPO FOR HOME SCREEN (Metadata)")
    print(f"    • Repository Name:  daily-kaam-logs")
    print(f"    • Create Folder:    work")
    print(f"    • Create File:      sys_patch.json")
    print(f"    • 🔗 FINAL URL:     https://raw.githubusercontent.com/{username}/daily-kaam-logs/main/work/sys_patch.json")
    
    print("\n📂  PART B: REPO FOR DOWNLOADS (Index)")
    print(f"    • Repository Name:  project-store-v9")
    print(f"    • Create Folder:    assets")
    print(f"    • Create File:      texture_map.json")
    print(f"    • 🔗 FINAL URL:     https://raw.githubusercontent.com/{username}/project-store-v9/main/assets/texture_map.json")
    
    print("\n" + "="*70)
    print("✅  INSTRUCTIONS:")
    print("1. Create a new GitHub account with the username above.")
    print("2. Create the two repositories shown above.")
    print("3. Upload your JSON files to the specific folders.")
    print("4. DONE! The Flutter App will automatically find this version.")
    print("="*70 + "\n")

# ==============================================================================
# 🚀 MAIN MENU
# ==============================================================================
def main():
    while True:
        print("\n👋 Hello Ayar! What do you want to do today?\n")
        print("   [1] 🤖 My Bot got Banned (Change Bot Only)")
        print("   [2] 👻 My GitHub got Banned (Generate New Version)")
        print("   [3] ❌ Exit")
        
        choice = input("\n👉 Select an option (1-3): ")
        
        if choice == '1':
            flow_change_bot_name()
        elif choice == '2':
            flow_change_github_account()
        elif choice == '3':
            print("Exiting... Stay Safe! 🛡️")
            break
        else:
            print("Invalid option. Please try again.")
        
        input("Press Enter to continue...")
        clear_screen()

if __name__ == "__main__":
    main()