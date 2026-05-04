# ⚡ VidAI — 60-Second Quick Start

## 1️⃣ Install & Run

```bash
# cd to backend
cd backend

# Install dependencies
pip install -r requirements.txt

# Set API key (REQUIRED)
export VIDEODB_API_KEY="your-api-key-here"

# Start the backend
uvicorn main:app --reload --port 8765
```

✅ **Should see:** `Uvicorn running on http://0.0.0.0:8765`

---

## 2️⃣ Verify It Works

```bash
# In another terminal, test health
curl http://localhost:8765/api/health | jq .success

# Expected: true
```

✅ **If you see:** `"success": true` → Backend is ready!

---

## 3️⃣ Test Demo

```bash
curl http://localhost:8765/api/demo?mode=student | jq .message
```

✅ **If you see:** Some message (e.g., "Demo loaded." or "static fallback") → Working!

---

## 4️⃣ Open Frontend

Navigate to:

```
http://localhost:8765
```

✅ **Should see:** VidAI UI (dark theme, search bar, upload button)

---

## 5️⃣ Test a Feature (Optional)

### Option A: Load Demo in UI

- Click "Load Demo" button
- Should play a video instantly (or show demo fallback)

### Option B: Search Example

```bash
curl "http://localhost:8765/api/search?video_id=any_id&query=test&mode=student" | jq .message
```

✅ **If you see:** Valid JSON with `.success` and `.message` → It works!

---

## ⚙️ Configuration (Optional)

```bash
# Timeout for long videos (seconds)
export VIDEODB_PROCESS_TIMEOUT_SEC=600

# Enable detailed logging
export LOG_LEVEL=DEBUG

# Pre-configured demo video
export VIDEODB_DEMO_VIDEO_ID="abc123xyz"
```

---

## 🆘 Troubleshooting

| Issue                    | Fix                                      |
| ------------------------ | ---------------------------------------- |
| `Set VIDEODB_API_KEY`    | Run: `export VIDEODB_API_KEY="your-key"` |
| Port 8765 already in use | Run: `uvicorn main:app --port 8766`      |
| Frontend blank page      | Check `/api/health` returns 200          |
| Demo shows "fallback"    | That's OK! Backend is working            |
| Search returns empty     | That's OK! Shows highlights instead      |
| Processing times out     | Try a shorter video (<5 min)             |

---

## ✅ Ready Checklist

- [ ] Backend starts without errors
- [ ] `/api/health` returns `success: true`
- [ ] `/api/demo` returns valid JSON
- [ ] Frontend loads at `http://localhost:8765`
- [ ] At least one mode works (student/creator/research)

---

## 🎯 What's Guaranteed

| Scenario            | Before          | Now ✅             |
| ------------------- | --------------- | ------------------ |
| No search results   | Crash           | Returns highlights |
| API timeout         | 503 error       | Demo fallback      |
| Invalid JSON        | Plaintext error | Structured JSON    |
| No transcript ready | Hangs           | Shows placeholder  |
| Backend down        | 502 error       | Demo works offline |
| Any exception       | 500 error       | Graceful fallback  |

---

## 📚 Full Docs

- **Setup guide:** See `HACKATHON_SETUP.md`
- **What changed:** See `CHANGES_SUMMARY.md`
- **API contract:** See `API_CONTRACT.md`

---

**You're ready! 🚀**

Next step: Open the frontend and try uploading a short video (YouTube link or MP4 file).
