"""
═══════════════════════════════════════════════════
  ADD STUDENT — Notes Distribution System
═══════════════════════════════════════════════════

Run this whenever a new student pays.

It automatically:
  → Creates a personal Drive folder for them
  → Shares it (view only, no download)
  → Backfills ALL existing files from _uploads
     so late-joining students get everything
  → Registers them in students.json

Filenames stay exactly as you uploaded them.
Watermark inside each page carries name + roll number.
"""

import io
import json
import os
from datetime import datetime
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

CONFIG_FILE      = "config.json"
STUDENTS_FILE    = "students.json"
TOKEN_FILE       = "token.json"
CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

WATERMARK_OPACITY   = 0.07
WATERMARK_FONT_SIZE = 36
WATERMARK_ANGLE     = 40


def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def create_student_folder(service, student_name, roll, parent_id):
    folder_name = f"{roll}_{student_name.replace(' ', '_')}"
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    return service.files().create(body=metadata, fields="id").execute().get("id")


def share_folder_with_student(service, folder_id, email):
    service.permissions().create(
        fileId=folder_id,
        body={"type": "user", "role": "reader", "emailAddress": email},
        sendNotificationEmail=False
    ).execute()
    # Note: copyRequiresWriterPermission is a file-only property and cannot
    # be set on folders. Download restriction is applied per-file at upload time.


def get_or_create_folder(service, name, parent_id):
    results = service.files().list(
        q=(f"'{parent_id}' in parents and name='{name}' and "
           f"mimeType='application/vnd.google-apps.folder' and trashed=false"),
        fields="files(id)"
    ).execute()
    existing = results.get("files", [])
    if existing:
        return existing[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    return service.files().create(body=metadata, fields="id").execute().get("id")


def resolve_path(service, root_folder_id, path):
    current = root_folder_id
    for folder_name in path:
        current = get_or_create_folder(service, folder_name, current)
    return current


def scan_uploads_recursive(service, folder_id, path=None):
    if path is None:
        path = []
    results = []
    items = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute().get("files", [])
    for item in items:
        if item["mimeType"] == "application/vnd.google-apps.folder":
            results.extend(scan_uploads_recursive(service, item["id"], path + [item["name"]]))
        elif item["mimeType"] == "application/pdf":
            results.append({
                "file_id"  : item["id"],
                "file_name": item["name"],
                "path"     : path
            })
    return results


def download_file(service, file_id):
    request    = service.files().get_media(fileId=file_id)
    buffer     = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def upload_file(service, file_bytes, filename, folder_id):
    metadata = {"name": filename, "parents": [folder_id]}
    media    = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype="application/pdf", resumable=True)
    file     = service.files().create(body=metadata, media_body=media, fields="id").execute()
    service.files().update(
        fileId=file.get("id"),
        body={"copyRequiresWriterPermission": True}
    ).execute()


def create_watermark_overlay(name, roll, width, height):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))
    c.setFillColor(Color(0, 0, 0, alpha=WATERMARK_OPACITY))
    c.setFont("Helvetica-Bold", WATERMARK_FONT_SIZE)
    for x in [width * 0.25, width * 0.75]:
        for y in [height * 0.2, height * 0.5, height * 0.8]:
            c.saveState()
            c.translate(x, y)
            c.rotate(WATERMARK_ANGLE)
            c.drawCentredString(0, 0, name)
            c.setFont("Helvetica", WATERMARK_FONT_SIZE - 10)
            c.drawCentredString(0, -(WATERMARK_FONT_SIZE + 4), roll)
            c.restoreState()
    c.save()
    packet.seek(0)
    return packet.read()


def watermark_pdf(pdf_bytes, name, roll):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        wm = create_watermark_overlay(name, roll, w, h)
        page.merge_page(PdfReader(io.BytesIO(wm)).pages[0])
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def backfill_existing_files(service, student, uploads_folder_id):
    """
    Sends watermarked copies of ALL existing _uploads files to the new student.
    Filename stays identical to the original — only the watermark inside changes.
    Existing students are not touched.
    """
    name    = student["name"]
    roll    = student["roll"]
    root_id = student["drive_folder_id"]

    print(f"\n🔄 Scanning _uploads for existing files to backfill...")
    all_pdfs = scan_uploads_recursive(service, uploads_folder_id)

    if not all_pdfs:
        print("   _uploads is empty — nothing to backfill.")
        print("   Any files you upload later will reach this student automatically.")
        return

    print(f"   Found {len(all_pdfs)} file(s) — sending all to {name}...\n")
    success = 0

    for pdf_info in all_pdfs:
        file_name    = pdf_info["file_name"]
        path         = pdf_info["path"]
        path_display = "/".join(path + [file_name]) if path else file_name

        try:
            pdf_bytes        = download_file(service, pdf_info["file_id"])
            wm_bytes         = watermark_pdf(pdf_bytes, name, roll)
            target_folder_id = resolve_path(service, root_id, path)
            upload_file(service, wm_bytes, file_name, target_folder_id)  # filename unchanged
            print(f"   ✅ {path_display}")
            success += 1
        except Exception as e:
            print(f"   ❌ {path_display} — {e}")

    print(f"\n   Backfill done — {success}/{len(all_pdfs)} files sent to {name}")


def main():
    print("\n═══════════════════════════════════════")
    print("  Add New Student — Notes System")
    print("═══════════════════════════════════════\n")

    config = load_json(CONFIG_FILE, {})
    if not config.get("students_folder_id"):
        print("❌ config.json not found. Run setup.py first.")
        return

    students = load_json(STUDENTS_FILE, [])

    print("Enter student details:")
    name  = input("  Full Name   : ").strip()
    roll  = input("  Roll Number : ").strip()
    email = input("  Gmail ID    : ").strip()

    for s in students:
        if s["roll"] == roll:
            print(f"\n⚠️  Roll number {roll} already registered: {s['name']}")
            confirm = input("   Add anyway? (y/n): ").strip().lower()
            if confirm != "y":
                print("Aborted.")
                return

    print("\n🔄 Connecting to Google Drive...")
    service = authenticate()

    print(f"📁 Creating private folder for {name}...")
    folder_id = create_student_folder(service, name, roll, config["students_folder_id"])

    print(f"🔒 Sharing with {email} (view only, no download)...")
    share_folder_with_student(service, folder_id, email)

    folder_link   = f"https://drive.google.com/drive/folders/{folder_id}"
    student_entry = {
        "name"              : name,
        "roll"              : roll,
        "email"             : email,
        "drive_folder_id"   : folder_id,
        "drive_folder_link" : folder_link,
        "added_on"          : datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    students.append(student_entry)
    save_json(STUDENTS_FILE, students)
    print(f"✅ Registered — {name} ({roll})")

    backfill_existing_files(service, student_entry, config["uploads_folder_id"])

    print(f"\n{'═' * 39}")
    print(f"   Total students : {len(students)}")
    print(f"\n📲 Send this link to {name}:")
    print(f"   {folder_link}")
    print(f"{'═' * 39}\n")


if __name__ == "__main__":
    main()