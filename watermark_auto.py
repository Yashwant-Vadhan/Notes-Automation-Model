"""
═══════════════════════════════════════════════════
  NOTES DISTRIBUTION SYSTEM — Yashwant Vadhan
  Auto Watermark + Drive Upload (with subfolders)
═══════════════════════════════════════════════════

Supports full folder/subfolder structure.
Whatever directory tree you create inside _uploads
is EXACTLY replicated in every student's folder.

_uploads is your permanent working library — files stay there forever.
processed_files.json (local, on your laptop) tracks what's already been
distributed so the same file is never sent twice.

Example:
  _uploads/
    DEV/
      Unit 1/
        notes.pdf        → each student gets DEV/Unit 1/RollNo_notes.pdf
      qp_answers.pdf     → each student gets DEV/RollNo_qp_answers.pdf
    CV/
      numericals.pdf     → each student gets CV/RollNo_numericals.pdf
"""

import io
import os
import json
import time
import logging
from datetime import datetime
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

CONFIG_FILE         = "config.json"
STUDENTS_FILE       = "students.json"
PROCESSED_LOG       = "processed_files.json"
TOKEN_FILE          = "token.json"
CREDENTIALS_FILE    = "credentials.json"

POLL_INTERVAL       = 60        # seconds between Drive checks
WATERMARK_OPACITY   = 0.07
WATERMARK_FONT_SIZE = 36
WATERMARK_ANGLE     = 40

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("automation.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────

def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError("credentials.json not found. See SETUP.md.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


# ─────────────────────────────────────────────
#  WATERMARKING
# ─────────────────────────────────────────────

def create_watermark_overlay(name: str, roll: str, width: float, height: float) -> bytes:
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


def watermark_pdf(pdf_bytes: bytes, name: str, roll: str) -> bytes:
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


# ─────────────────────────────────────────────
#  DRIVE — FOLDER OPERATIONS
# ─────────────────────────────────────────────

def list_folder_contents(service, folder_id: str) -> list:
    """Lists all files AND subfolders inside a Drive folder (non-recursive)."""
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get("files", [])


def scan_uploads_recursive(service, folder_id: str, path: list = None) -> list:
    """
    Recursively scans _uploads folder and returns all PDFs with their folder path.

    Returns list of:
    {
        "file_id"   : "...",
        "file_name" : "notes.pdf",
        "path"      : ["DEV", "Unit 1"]   ← folders relative to _uploads root
    }
    """
    if path is None:
        path = []

    results = []
    items = list_folder_contents(service, folder_id)

    for item in items:
        if item["mimeType"] == "application/vnd.google-apps.folder":
            # Recurse into subfolder
            subfolder_path = path + [item["name"]]
            results.extend(scan_uploads_recursive(service, item["id"], subfolder_path))
        elif item["mimeType"] == "application/pdf":
            results.append({
                "file_id"   : item["id"],
                "file_name" : item["name"],
                "path"      : path          # e.g. ["DEV", "Unit 1"]
            })

    return results


def get_or_create_folder(service, name: str, parent_id: str) -> str:
    """
    Returns the ID of a folder named `name` inside `parent_id`.
    Creates it if it doesn't exist.
    """
    # Check if folder already exists
    results = service.files().list(
        q=(
            f"'{parent_id}' in parents and "
            f"name='{name}' and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"trashed=false"
        ),
        fields="files(id, name)"
    ).execute()

    existing = results.get("files", [])
    if existing:
        return existing[0]["id"]

    # Create it
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder.get("id")


def resolve_path_in_student_folder(service, student_folder_id: str, path: list) -> str:
    """
    Given a path like ["DEV", "Unit 1"], ensures those nested folders exist
    inside the student's folder and returns the ID of the deepest folder.

    If path is empty, returns the student's root folder ID.
    """
    current_folder_id = student_folder_id
    for folder_name in path:
        current_folder_id = get_or_create_folder(service, folder_name, current_folder_id)
    return current_folder_id


# ─────────────────────────────────────────────
#  DRIVE — FILE OPERATIONS
# ─────────────────────────────────────────────

def download_file(service, file_id: str) -> bytes:
    request    = service.files().get_media(fileId=file_id)
    buffer     = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def upload_file(service, file_bytes: bytes, filename: str, folder_id: str) -> str:
    metadata = {"name": filename, "parents": [folder_id]}
    media    = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype="application/pdf", resumable=True)
    file     = service.files().create(body=metadata, media_body=media, fields="id").execute()
    file_id  = file.get("id")

    # Disable download / copy / print for viewers
    service.files().update(
        fileId=file_id,
        body={"copyRequiresWriterPermission": True}
    ).execute()

    return file_id



# ─────────────────────────────────────────────
#  CORE PIPELINE
# ─────────────────────────────────────────────

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def process_file(service, pdf_info: dict, config: dict, students: list, processed_log: set):
    """
    Full pipeline for one PDF:
      Download → watermark per student → upload to correct subfolder → log locally
    Original stays in _uploads permanently as your clean reference library.
    """
    file_id   = pdf_info["file_id"]
    file_name = pdf_info["file_name"]
    path      = pdf_info["path"]         # e.g. ["DEV", "Unit 1"]

    path_display = "/".join(path + [file_name]) if path else file_name

    if file_id in processed_log:
        return

    log.info(f"🆕 New file: {path_display}")

    # Download
    try:
        pdf_bytes = download_file(service, file_id)
        log.info(f"   ✅ Downloaded ({len(pdf_bytes) // 1024} KB)")
    except Exception as e:
        log.error(f"   ❌ Download failed: {e}")
        return

    # Watermark + upload per student
    success = 0
    for student in students:
        name      = student["name"]
        roll      = student["roll"]
        root_id   = student["drive_folder_id"]

        try:
            # Mirror the subfolder path inside student's folder
            target_folder_id = resolve_path_in_student_folder(service, root_id, path)

            # Watermark
            wm_bytes  = watermark_pdf(pdf_bytes, name, roll)
            wm_name   = file_name

            # Upload
            upload_file(service, wm_bytes, wm_name, target_folder_id)
            log.info(f"   📤 → {name} ({roll})  [{path_display}]")
            success += 1

        except Exception as e:
            log.error(f"   ❌ Failed for {name}: {e}")

    processed_log.add(file_id)
    log.info(f"✅ Done — {success}/{len(students)} students  |  {path_display}  |  original kept in _uploads\n")


def run():
    log.info("═" * 55)
    log.info("  Notes Distribution System — Starting")
    log.info("  Subfolder mirroring: ENABLED")
    log.info("═" * 55)

    config = load_json(CONFIG_FILE, {})
    if not config.get("uploads_folder_id"):
        log.error("config.json missing. Run setup.py first.")
        return

    try:
        service = authenticate()
        log.info("✅ Google Drive authenticated")
    except Exception as e:
        log.error(f"Auth failed: {e}")
        return

    processed_log = set(load_json(PROCESSED_LOG, []))
    log.info(f"✅ {len(processed_log)} files already processed")
    log.info(f"👀 Watching _uploads every {POLL_INTERVAL}s — Ctrl+C to stop\n")

    try:
        while True:
            students = load_json(STUDENTS_FILE, [])

            if not students:
                log.warning("No students registered. Run add_student.py first.")
            else:
                # Recursively scan entire _uploads tree
                all_pdfs = scan_uploads_recursive(service, config["uploads_folder_id"])
                new_pdfs = [f for f in all_pdfs if f["file_id"] not in processed_log]

                if new_pdfs:
                    log.info(f"Found {len(new_pdfs)} new file(s) across all subfolders")
                    for pdf_info in new_pdfs:
                        process_file(service, pdf_info, config, students, processed_log)
                    save_json(PROCESSED_LOG, list(processed_log))
                else:
                    log.info("No new files. Waiting...")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info("\n👋 Stopping...")
        save_json(PROCESSED_LOG, list(processed_log))
        log.info("Saved. Goodbye.")


if __name__ == "__main__":
    run()
