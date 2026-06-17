# Notes Distribution System

A Python automation tool for distributing personalized, watermarked study notes to students via Google Drive.

## What it does

Upload a PDF once to your `_uploads` folder — the system automatically:
- Watermarks it with each student's name and roll number (embedded inside every page)
- Mirrors your exact folder/subfolder structure into each student's private Drive folder
- Delivers it to every registered student within 60 seconds
- Backfills all existing files when a new student is added late
- Keeps `_uploads` as your permanent clean library — nothing is moved or deleted

## Folder structure on Google Drive

```
📁 Notes Hub
   📁 _uploads            ← you upload PDFs here (permanent library)
   📁 Students
      📁 2024510001_Name  ← shared only with that student's Gmail
      📁 2024510002_Name
```

Each student's folder mirrors _uploads exactly:
```
_uploads/DEV/Unit1/notes.pdf  →  StudentFolder/DEV/Unit1/notes.pdf
```

## Files

| File | Purpose |
|---|---|
| `setup.py` | One-time setup — creates Drive folder structure |
| `add_student.py` | Register a new student + backfill all existing files |
| `watermark_auto.py` | Background watcher — runs continuously, processes new uploads |

## Setup

### 1. Install dependencies

```bash
pip install pypdf reportlab google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### 2. Get Google API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable **Google Drive API**
4. Go to **Credentials → OAuth Client ID → Desktop App**
5. Download the file and rename it to `credentials.json`
6. Place it in the same folder as these scripts

### 3. Run first-time setup

```bash
python setup.py
```

Browser opens → log in → Drive folders are created → `config.json` saved automatically.

### 4. Add students

```bash
python add_student.py
```

Enter their name, roll number, and Gmail. Their private Drive folder is created, shared, and all existing files are backfilled automatically.

### 5. Start the automation

```bash
python watermark_auto.py
```

Leave this running. Drop any PDF into `_uploads` on Drive and it reaches every student within 60 seconds.

## How watermarking works

Every student receives the **same filename** as the original upload. However, their name and roll number are embedded as a diagonal watermark across every page. If a file is ever leaked or shared, the watermark identifies exactly who distributed it.

## Access control

- Students receive a **view-only** link to their private folder
- Download, print, and copy are disabled at the file level
- Access can be revoked anytime from Google Drive
- Only registered Gmail IDs can open the folder

## Local files (do not delete)

| File | Purpose |
|---|---|
| `config.json` | Stores your Drive folder IDs |
| `students.json` | Registry of all registered students |
| `processed_files.json` | Tracks which files have been distributed — prevents duplicates |
| `token.json` | Saved Google auth token — avoids re-login every run |

## Tech stack

- **Python 3.x**
- **pypdf** — PDF reading and page merging
- **ReportLab** — Watermark generation
- **Google Drive API v3** — File upload, folder management, permission control
