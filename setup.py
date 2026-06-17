"""
═══════════════════════════════════════════════════
  FIRST TIME SETUP — Notes Distribution System
═══════════════════════════════════════════════════

Run this ONCE before anything else.

What it does:
  → Connects to your Google Drive
  → Creates the full folder structure
  → Saves folder IDs in config.json

Run:
  python setup.py
"""

import json
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_FILE       = "token.json"
CREDENTIALS_FILE = "credentials.json"
CONFIG_FILE      = "config.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print("❌ credentials.json not found!")
                print("   Follow SETUP.md to get it from Google Cloud Console.")
                exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def create_folder(service, name: str, parent_id: str = None) -> str:
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder.get("id")


def main():
    print("\n═══════════════════════════════════════════")
    print("  Notes Distribution System — First Setup")
    print("═══════════════════════════════════════════\n")

    if os.path.exists(CONFIG_FILE):
        print("⚠️  config.json already exists. Setup was already done.")
        redo = input("   Run setup again and overwrite? (y/n): ").strip().lower()
        if redo != "y":
            print("Exiting. Your existing config is unchanged.")
            return

    print("🔄 Opening browser for Google authentication...")
    service = authenticate()
    print("✅ Authenticated!\n")

    print("📁 Creating folder structure on your Google Drive...\n")

    # Master folder
    master_id = create_folder(service, "Notes Hub")
    print(f"   ✅ Notes Hub (master folder)")

    # Subfolders
    uploads_id   = create_folder(service, "_uploads", master_id)
    print(f"   ✅ _uploads  ← your permanent notes library, files stay here forever")

    students_id  = create_folder(service, "Students", master_id)
    print(f"   ✅ Students  ← individual student folders will appear here")

    # Save config
    config = {
        "master_folder_id"   : master_id,
        "uploads_folder_id"  : uploads_id,
        "students_folder_id" : students_id
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ config.json saved.")
    print(f"\n🎉 Setup complete! Here's your Drive structure:")
    print(f"   📁 Notes Hub")
    print(f"      📁 _uploads      → https://drive.google.com/drive/folders/{uploads_id}")
    print(f"      📁 Students")
    print(f"\nNext steps:")
    print(f"  1. Add students     → python add_student.py")
    print(f"  2. Start automation → python watermark_auto.py")
    print(f"  3. Upload a PDF to '_uploads' and watch it go!")
    print("═══════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
