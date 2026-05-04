# VidAI API Contract — Frontend Developer Guide

**Backend Status:** ✅ Stable (Never crashes, always returns valid JSON)

---

## 🎯 API Guarantees

Every endpoint returns:

- **Valid JSON** (never plaintext)
- **200 status** (success or graceful failure)
- **`success` field** (true/false)
- **`message` field** (user-friendly text)
- **Fallback data** if needed

---

## 📋 Endpoint Reference

### 1. **POST /api/process** | Ingest & Index

**Input:**

```json
{
  "url": "https://youtube.com/watch?v=...",
  "mode": "student"
}
```

**Success (202s, video ready):**

```json
{
  "success": true,
  "video_id": "abc123xyz",
  "name": "My Video Title",
  "stream_url": "https://cdn.videodb.io/...",
  "transcript_text": "... full transcript ...",
  "transcript_segments": [
    { "start": 0.0, "end": 5.2, "text": "..." },
    { "start": 5.2, "end": 12.8, "text": "..." }
  ],
  "highlights": [{ "start": 15.0, "end": 22.0, "text": "Key moment" }],
  "mode": "student",
  "ready": true,
  "message": "Processed."
}
```

**Timeout (420s exceeded):**

```json
{
  "success": false,
  "video_id": "",
  "stream_url": "",
  "demo": true,
  "fallback": true,
  "message": "Processing exceeded 420s limit. Try a shorter clip.",
  "ready": false
}
```

**UI Handling:**

```javascript
// Always safe — check success flag
if (response.success) {
  videoId = response.video_id;
  playVideo(response.stream_url);
} else if (response.fallback) {
  showMessage("Your video is being processed. Here's a demo:");
  playDemoVideo();
}
```

---

### 2. **GET /api/demo** | Load Demo

**Input:**

```
/api/demo?mode=student
```

**Success (live demo video):**

```json
{
  "success": true,
  "video_id": "abc123xyz",
  "name": "Demo Video",
  "stream_url": "https://...",
  "transcript_text": "...",
  "highlights": [{ "start": 10, "end": 20, "text": "Viral moment" }],
  "mode": "student",
  "ready": true,
  "demo": true,
  "message": "Demo loaded."
}
```

**Fallback (static demo):**

```json
{
  "success": true,
  "video_id": "",
  "stream_url": "",
  "demo": true,
  "fallback": true,
  "message": "Demo video unavailable, showing static fallback.",
  "highlights": []
}
```

**UI Handling:**

```javascript
// Always safe — demo always works
displayDemo(response); // Never fails
```

---

### 3. **GET /api/search** | Query Video

**Input:**

```
/api/search?video_id=abc123&query=leadership&mode=student
```

**Keyword Match Found:**

```json
{
  "success": true,
  "message": "Exact match found.",
  "ready": true,
  "query": "leadership",
  "shots": [
    { "start": 45.2, "end": 58.9, "text": "Leadership is..." },
    { "start": 120.0, "end": 135.0, "text": "How to lead..." }
  ],
  "fallback_used": null,
  "search_path": "keyword"
}
```

**No Match, Highlights Returned:**

```json
{
  "success": true,
  "message": "No exact match — showing curated highlights instead.",
  "ready": true,
  "query": "xyz123",
  "shots": [{ "start": 10.0, "end": 20.0, "text": "Key moment" }],
  "fallback_used": "highlights"
}
```

**Transcript Not Ready Yet:**

```json
{
  "success": true,
  "message": "Video still processing. Please wait.",
  "ready": false,
  "query": "leadership",
  "shots": [{ "start": 0.0, "end": 5.0, "text": "Segment 1" }],
  "fallback_used": "not_ready_slices"
}
```

**UI Handling:**

```javascript
// ALWAYS has shots — never empty
displayShots(response.shots);

// Check ready & ready status
if (!response.ready) {
  showSpinner("Still indexing...");
}

// Use fallback_used for analytics
if (response.fallback_used) {
  console.log("Used fallback:", response.fallback_used);
}
```

---

### 4. **POST /api/videos/{video_id}/search** | Search (POST)

Same as GET `/api/search` but uses JSON body:

```json
{
  "query": "leadership"
}
```

---

### 5. **GET /api/reel** | Compile Highlights into Reel

**Input:**

```
/api/reel?video_id=abc123&mode=student
```

**Success:**

```json
{
  "success": true,
  "stream_url": "https://...",
  "clips": [
    { "start": 10, "end": 20, "text": "..." },
    { "start": 45, "end": 60, "text": "..." }
  ],
  "message": "Reel compiled successfully."
}
```

**Failure (graceful):**

```json
{
  "success": false,
  "stream_url": "",
  "clips": [],
  "message": "Reel generation failed: API timeout"
}
```

**UI Handling:**

```javascript
if (response.success && response.stream_url) {
  playReel(response.stream_url);
} else {
  showMessage("Reel unavailable. Try individual clips.");
}
```

---

### 6. **POST /api/videos/{video_id}/reel** | Custom Reel

**Input:**

```json
{
  "clips": [
    { "start": 10, "end": 20, "text": "Intro" },
    { "start": 45, "end": 60, "text": "Key point" }
  ]
}
```

**Success/Failure:** Same as GET `/api/reel`

---

### 7. **GET /api/summary** | AI Summary

**Input:**

```
/api/summary?video_id=abc123&mode=student
```

**Success (AI-generated):**

```json
{
  "success": true,
  "bullets": "## Bullet notes\n- Point 1\n- Point 2\n## Key takeaways\n- Takeaway",
  "mode": "student",
  "ready": true,
  "message": "Summary generated."
}
```

**Not Ready:**

```json
{
  "success": false,
  "message": "Transcript still processing.",
  "bullets": "",
  "ready": false
}
```

**API Quota Exceeded (Fallback):**

```json
{
  "success": true, // Note: still true!
  "bullets": "## Bullet notes\n- Transcript excerpts remain searchable.",
  "mode": "student",
  "ready": false,
  "message": "Summary used offline template."
}
```

**UI Handling:**

```javascript
if (response.bullets) {
  displayMarkdown(response.bullets);
}

if (!response.ready) {
  showMessage("Summary unavailable, retrying...");
  setTimeout(() => fetchSummary(), 2000);
}
```

---

### 8. **POST /api/videos/{video_id}/summary** | Summary (POST)

Same as GET but with JSON body:

```json
{
  "mode": "student"
}
```

---

### 9. **GET /api/videos/{video_id}/clip-stream** | Single Clip

**Input:**

```
/api/videos/abc123/clip-stream?start=10.0&end=25.5
```

**Success:**

```json
{
  "success": true,
  "stream_url": "https://...",
  "message": "Clip compiled."
}
```

---

### 10. **GET /api/videos/{video_id}/subtitles-stream** | Subtitles

**Input:**

```
/api/videos/abc123/subtitles-stream
```

**Success/Failure:** Same structure as clip-stream

---

### 11. **GET /api/health** | Backend Status

**Input:**

```
/api/health
```

**Response:**

```json
{
  "success": true,
  "message": "ok",
  "videodb_api_key_present": true,
  "demo_video_configured": false,
  "process_timeout_sec": 420
}
```

**UI Use:**

```javascript
// Check health on app load
if (!response.videodb_api_key_present) {
  showError("Backend not configured. Contact admin.");
}
```

---

## 🎯 Frontend Workflow

### Standard Flow

```javascript
// 1. Load demo (always works)
const demo = await fetch("/api/demo?mode=student");
displayVideo(demo.stream_url);

// 2. User uploads video
const upload = await fetch("/api/process/upload", {
  method: "POST",
  body: formData,
});
if (upload.success) {
  videoId = upload.video_id;
}

// 3. User searches
const results = await fetch(`/api/search?video_id=${videoId}&query=...`);
displayClips(results.shots); // Always has clips

// 4. Make reel
const reel = await fetch(`/api/reel?video_id=${videoId}`);
if (reel.stream_url) {
  playReel(reel.stream_url);
}

// 5. Get summary
const summary = await fetch(`/api/summary?video_id=${videoId}`);
if (summary.ready) {
  displayMarkdown(summary.bullets);
}
```

### Error Handling Pattern

```javascript
async function safeFetch(url, init = {}) {
  try {
    const resp = await fetch(url, init);
    const json = await resp.json();

    if (resp.ok && json.success) {
      return json; // All good
    } else if (json.success === false) {
      console.warn("Graceful failure:", json.message);
      return json; // Backend handled it
    } else {
      console.error("Unexpected response:", json);
      return null;
    }
  } catch (err) {
    console.error("Network error:", err);
    return null; // Show fallback UI
  }
}

// Usage
const data = await safeFetch("/api/demo?mode=student");
if (data) {
  displayVideo(data);
} else {
  showOfflineUI(); // Never crashes
}
```

---

## 🔑 Key Principles for Frontend

### 1. Check `success` Field

```javascript
if (response.success) {
  // Use response.data
} else {
  // Show response.message or fallback
}
```

### 2. Always Have Data

```javascript
// These ALWAYS exist (never null):
response.message; // Helpful user text
response.ready; // boolean
response.shots; // array (might be empty if fallback)
response.stream_url; // string (might be empty)
```

### 3. Fallback System

```javascript
// If search fails:
1. Shows highlights (pre-computed)
2. Shows transcript slices
3. Shows synthetic timeline (always works)
// Never empty

// If summary fails:
1. Shows offline template
2. Suggests retry
// Never crashes
```

### 4. Ready Status

```javascript
if (response.ready === false) {
  // Transcript still processing
  showSpinner("Indexing video...");
  setTimeout(() => retry(), 3000); // Safe retry
}
```

### 5. Timeouts

- **Processing (upload):** Max 420s → shows demo fallback
- **Search:** Should be <2s (cached)
- **Summary:** Should be <5s (may use offline template)
- **Demo:** Max 30s → always shows fallback

---

## 🎬 Mode Handling

### Modes Supported

- `student` → Education-focused highlights & tone
- `creator` → Viral/shareable moments
- `research` → Evidence & methodology

### Default

If mode not specified or invalid → defaults to `student`

### Usage

```javascript
const response = await fetch(`/api/search?mode=${selectedMode}`);
// Server normalizes invalid modes safely
```

---

## 🆘 Common Frontend Scenarios

### Scenario 1: "Show Me a Demo"

```javascript
const demo = await fetch("/api/demo?mode=student");
playVideo(demo.stream_url); // Always works
```

### Scenario 2: "Search for Leadership"

```javascript
const results = await fetch(`/api/search?video_id=${id}&query=leadership`);
displayClips(results.shots); // Always has clips
console.log(results.fallback_used); // Log what worked
```

### Scenario 3: "Make a Reel of Highlights"

```javascript
const reel = await fetch(`/api/reel?video_id=${id}&mode=creator`);
if (reel.stream_url) {
  playReel(reel.stream_url);
} else {
  showMessage(reel.message); // Helpful fallback message
}
```

### Scenario 4: "Summarize This Video"

```javascript
const summary = await fetch(`/api/summary?video_id=${id}&mode=student`);
if (summary.ready) {
  displayMarkdown(summary.bullets);
} else {
  showMessage("Still processing, try in a few seconds...");
}
```

### Scenario 5: "Backend is Down"

```javascript
// Demo endpoint always works:
const demo = await fetch("/api/demo");
showOfflineMode(demo); // Graceful degradation
```

---

## 📊 Response Checklist

Every response has:

- ✅ `success` (boolean)
- ✅ `message` (user-friendly string)
- ✅ Relevant data fields (shots, stream_url, bullets, etc.)
- ✅ Valid JSON (never plaintext)
- ✅ 200 status (even on errors)\*\*

---

**TL;DR:** Backend always returns valid JSON with helpful fallbacks. Frontend can always display something meaningful, never worry about crashes or empty responses.
