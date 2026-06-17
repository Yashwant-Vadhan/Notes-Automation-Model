# Notes Distribution System — Setup Guide
### Yashwant Vadhan

---

## What you need before starting
- Python installed on your laptop
- A Google account (your main one)
- 10 minutes for the one-time setup

---

## Step 1 — Install Python libraries

Open terminal and run:
```
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 pypdf reportlab
```

---

## Step 2 — Get your Google API credentials (one time only)

1. Go to → https://console.cloud.google.com/
2. Click **"New Project"** → name it `Notes System` → Create
3. In the left menu go to **APIs & Services → Library**
4. Search **"Google Drive API"** → Click it → Click **Enable**
5. Now go to **APIs & Services → OAuth consent screen**
   - Choose **External** → Click Create
   - App name: `Notes System`
   - Your email for support → Save and Continue (skip the rest, just save)
6. Go to **APIs & Services → Credentials**
   - Click **+ Create Credentials → OAuth Client ID**
   - Application type: **Desktop App**
   - Name: `Notes System` → Create
7. Click the **Download** button (⬇) on the created credential
8. Rename the downloaded file to `credentials.json`
9. Place `credentials.json` in the same folder as these scripts

---

## Step 3 — First time setup (creates Drive folders)

```
python setup.py
```

- Your browser will open asking you to log in to Google
- Log in with your Google account and click **Allow**
- This creates the folder structure on your Drive automatically
- A `config.json` will be saved — don't delete it

---

## Step 4 — Add your first student

```
python add_student.py
```

- Enter their name, roll number, and Gmail ID
- Their private Drive folder is created and shared automatically
- Copy the folder link shown and send it to them on WhatsApp

---

## Step 5 — Start the automation

```
python watermark_auto.py
```

- Leave this running on your laptop
- It checks for new files every 60 seconds
- When you drop a PDF into `_uploads`, it processes automatically

---

## Day-to-day usage

| What you want to do | Command |
|---|---|
| Start the automation | `python watermark_auto.py` |
| Register a new student | `python add_student.py` |
| Check logs | Open `automation.log` |

**Uploading notes:**
1. Go to your Google Drive → Notes Hub → _uploads
2. Drag and drop your PDF there
3. Within 60 seconds, every student's folder gets their watermarked copy

---

## Removing a student's access

1. Go to Google Drive → Notes Hub → Students
2. Right-click their folder → Share → Remove their email
3. Delete them from `students.json` (open with Notepad)

---

## Folder structure on your Drive

```
📁 Notes Hub
   📁 _uploads       ← YOU upload PDFs here
   📁 _processed     ← auto-moved after processing
   📁 Students
      📁 21CS101_Arun_Kumar     ← Arun sees only this
      📁 21CS102_Priya_Sharma   ← Priya sees only this
```

---

## Troubleshooting

**"credentials.json not found"**
→ Make sure the file is in the same folder as the scripts

**"No module named googleapiclient"**
→ Run the pip install command from Step 1 again

**Files not being processed**
→ Check `automation.log` for error messages
→ Make sure `watermark_auto.py` is still running

**Student says they can download the file**
→ The download is disabled at upload time. If they had access before this system, revoke and re-share.
