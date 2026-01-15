def generate_ghost_identity(version):
    """
    Generates the Username based on the Flutter App's Logic.
    Logic: OtaNexaAhirServer{num1}LogKeeper{num2}TNExNGitQ{suffix}
    """
    
    # 1. Num1 Logic: If Version 1 -> 0, Else -> Version Number
    if version == 1:
        num1 = 0
    else:
        num1 = version

    # 2. Num2 Logic: If Even -> 0, If Odd -> Version - 1
    if version % 2 == 0:
        num2 = 0
    else:
        num2 = version - 1

    # 3. Suffix Logic (Quadratic Formula)
    # Formula: 6814 + (v * 19) + (v^2 * 7)
    v = version - 1
    suffix = 6814 + (v * 19) + (v * v * 7)

    # Construct the Username
    username = f"OtaNexaAhirServer{num1}LogKeeper{num2}TNExNGitQ{suffix}"
    return username

def print_details(version):
    username = generate_ghost_identity(version)
    bot_name = f"@{username}_bot"
    
    print(f"\n{'='*60}")
    print(f"👻  GHOST VERSION {version} (Create these accounts)")
    print(f"{'='*60}")
    print(f"👤 GitHub Username:   {username}")
    print(f"🤖 Default Bot Name:  {bot_name}")
    print(f"{'-'*60}")
    
    print(f"📂 REPO 1: HOME SCREEN DATA (AnimeRepository)")
    print(f"   • Create Repo:   daily-kaam-logs")
    print(f"   • Create File:   work/sys_patch.json")
    print(f"   • Final URL:     https://raw.githubusercontent.com/{username}/daily-kaam-logs/main/work/sys_patch.json")
    
    print(f"\n📂 REPO 2: DOWNLOAD INDEX (AnimeDownloadService)")
    print(f"   • Create Repo:   project-store-v9")
    print(f"   • Create File:   assets/texture_map.json")
    print(f"   • Final URL:     https://raw.githubusercontent.com/{username}/project-store-v9/main/assets/texture_map.json")

# --- RUN THIS LOOP ---
if __name__ == "__main__":
    print("Generating Backup Identities for OtakuNexa...\n")
    
    # Change the range to generate more versions (e.g., 1 to 6)
    # Currently generating Version 1 (Active) to Version 3 (Backups)
    for i in range(1, 4): 
        print_details(i)