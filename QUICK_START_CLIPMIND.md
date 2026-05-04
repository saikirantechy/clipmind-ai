# 🚀 ClipMind AI — Quick Start (2 Minutes)

## Step 1️⃣ Start Backend

```bash
cd "c:\Users\saiki\VideoDB Co-Work Blr"
python -m uvicorn backend.clipmind:app --reload --port 8766
```

**Expected output:**

```
INFO:     Uvicorn running on http://127.0.0.1:8766
INFO:     Application startup complete.
```

## Step 2️⃣ Open Frontend

- **Option A:** Double-click `frontend/clipmind.html`
- **Option B:** Open in VS Code > Right-click > "Open with Live Server"
- **Option C:** Direct address bar: `file:///c:/Users/saiki/VideoDB Co-Work Blr/frontend/clipmind.html`

## Step 3️⃣ Click "Load Demo"

Watch it load sample video with:

- ✅ 4 pre-configured clips
- ✅ 350-character transcript
- ✅ Working search
- ✅ Live summary generation
- ✅ Reel creation

## Step 4️⃣ Try Features

**Search:** Type "introduction" or "system" in search box
**Mode:** Switch between Student/Creator/Research
**Summary:** Click "Generate Summary" for AI insights
**Reel:** Click "Create Reel" to compile highlights

---

## 📺 Live Demo without Internet

✅ Works 100% offline
✅ No API keys needed
✅ Instant loading
✅ Full feature showcase

---

## 🔗 API Endpoints (For Advanced Users)

```bash
# Health check
curl http://localhost:8766/health

# Load demo
curl http://localhost:8766/demo?mode=student

# Search
curl "http://localhost:8766/search?q=introduction&mode=student"

# Status
curl http://localhost:8766/status
```

---

## 📝 To Use Real Videos

1. Get API keys:
   - VideoDB: videodb.io/register
   - Google Gemini: makersuite.google.com/app/apikey

2. Edit `.env`:

   ```env
   VIDEODB_API_KEY=your_real_key
   GEMINI_API_KEY=your_real_key
   ```

3. Restart backend (Ctrl+C, then run command again)

4. Paste YouTube URL in "Video Source" field

---

## ✅ System Check

**If you see this in terminal:**

```
INFO:     Application startup complete.
```

✅ Everything is working!

**Quick test:**

```
http://localhost:8766/health
```

Should return valid JSON with `"success": true`

---

## 🎯 Demo Highlights

The pre-loaded demo includes:

- Video: "ClipMind AI Demo — Understanding Video AI"
- Transcript: 350 characters of sample content
- Clips: 4 time-keyed moments
- Works: Every button, every feature

Perfect for:

- Quick demo to judges
- Testing UI before connecting real videos
- Understanding features without setup hassle

---

## 💡 Pro Tips

1. **Dark theme** works great in dimly-lit demo rooms
2. **Search twice** on same query to test fallback behavior
3. **Mode switching** shows different summaries
4. **Status shows** current state (idle/processing/ready)
5. **Error messages** are helpful, not scary

---

## 📊 Project Files

```
frontend/
  └── clipmind.html               ← Open this!

backend/
  ├── clipmind.py                 ← Run this!
  ├── requirements_clipmind.txt   ← Already installed
  └── README_CLIPMIND.md          ← Full documentation

.env                              ← Has API key placeholders
CLIPMIND_COMPLETION.md            ← Detailed project info
QUICK_START.md                    ← This file!
```

---

## 🆘 Troubleshooting

**"Port 8766 already in use"**

```bash
# Use different port
python -m uvicorn backend.clipmind:app --port 8767
# Then update HTML to use: http://localhost:8767
```

**"Frontend shows connecting... forever"**

```bash
# Verify backend is running
curl http://localhost:8766/health
# Should return JSON immediately
```

**"Search returns no results"**
✅ This is normal! Demo data has limited content
✅ Use keywords from demo: "introduction", "welcome", "system", "AI"

**"Button doesn't work"**
✅ Check browser console (F12) for errors
✅ Verify backend is running
✅ Try "Load Demo" first to test connectivity

---

## 🎉 You're Ready!

That's it! Your ClipMind AI hackathon demo is ready to impress.

- No complicated setup
- Works offline
- Professional appearance
- All features working

**Click "Load Demo" and watch the magic! ✨**

---

_Built for hackathons. Designed to wow judges._
