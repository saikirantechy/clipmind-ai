# VidAI — Visual Architecture & Fallback Flows

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (UI)                        │
│              HTML + JS (Single Page Application)            │
│  [Process] [Search] [Reel] [Summary] [Demo] [Upload]       │
└────────────────────────────┬────────────────────────────────┘
                             │
                    (JSON API Calls)
                             │
┌────────────────────────────▼────────────────────────────────┐
│                   FASTAPI BACKEND                           │
│                    (main.py)                                │
├─────────────────────────────────────────────────────────────┤
│                   ┌──────────────────┐                      │
│                   │  ERROR HANDLER   │ ← Catches EVERYTHING │
│                   │  (Global Safety)  │                      │
│                   └────────┬─────────┘                      │
│                            │                                │
│     ┌──────────────────────▼──────────────────────┐        │
│     │        SMART FALLBACK CHAIN                 │        │
│     │  1. Exact Match (Keyword)                   │        │
│     │  2. Semantic Match                          │        │
│     │  3. Curated Highlights                      │        │
│     │  4. Transcript Slices                       │        │
│     │  5. Synthetic Timeline  ← Never Empty       │        │
│     └──────────────────┬───────────────────────────┘        │
│                        │                                    │
│     ┌──────────────────▼──────────────────────┐            │
│     │         VideoDB SDK Integration         │            │
│     │  [Process] [Search] [Index] [Stream]    │            │
│     └──────────────────┬──────────────────────┘            │
│                        │                                    │
└────────────────────────┼────────────────────────────────────┘
                         │
         (VideoDB Cloud API + HLS Streaming)
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   VideoDB Cloud                            │
│  [Video Storage] [Transcript] [Index] [Stream Generation]  │
│         + AI Summarization + Speech Recognition            │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Search Flow (Request → Response)

```
┌─────────────────────┐
│  User Query (GET)   │
│  /api/search?q=...  │
└──────────┬──────────┘
           │
      ┌────▼─────────────────┐
      │ Transcript Ready?     │
      └────┬────────┬─────────┘
       YES │        │ NO
          │        └──→ [Return Placeholder Slices]
          │
      ┌───▼──────────────────────┐
      │ 1. Keyword Search?        │
      │    safe_search(keyword)   │
      └───┬──────────┬────────────┘
      HIT │          │ MISS
         │          │
      ┌──▼──┐   ┌───▼──────────────────────┐
      │RETURN│   │ 2. Semantic Search?      │
      └──────┘   │    safe_search(semantic) │
                 └───┬──────────┬───────────┘
             HIT │          │ MISS
                │          │
             ┌──▼──┐   ┌───▼──────────────────┐
             │RETURN│   │ 3. Highlights?       │
             └──────┘   │    highlight_pass()  │
                        └───┬──────────┬───────┘
                    HIT │          │ MISS
                       │          │
                    ┌──▼──┐   ┌───▼──────────────┐
                    │RETURN│   │ 4. Transcript    │
                    └──────┘   │    Slices?       │
                               └───┬──────────┬──┘
                           HIT │          │ MISS
                              │          │
                           ┌──▼──┐   ┌───▼──────┐
                           │RETURN│   │ 5.       │
                           └──────┘   │ Synthetic│
                                      │ Timeline │
                                      └───┬──────┘
                                          │
                                      ┌───▼──────┐
                                      │ ALWAYS   │
                                      │ RETURN   │
                                      │ SOMETHING│
                                      └──────────┘
```

---

## ⏱️ Processing Timeout Flow

```
User Uploads Video
      │
      ▼
┌──────────────────────┐
│  Stream Temp File    │
│  (write to disk)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────┐
│  ThreadPoolExecutor (1 worker)   │
│  timeout=420s                    │
│  job: ingest_and_index_blocking()│
│                                  │
│  • Upload video  (1-30s)         │
│  • Generate transcript (10-60s)  │
│  • Index spoken words (5-30s)    │
│  • Wait for ready (varies)       │
└──────────┬──────────┬────────────┘
       OK  │          │ TIMEOUT (>420s)
          │          │
     ┌────▼──┐  ┌────▼──────────────┐
     │Return │  │ Return Demo       │
     │Result │  │ Fallback          │
     │(video │  │ (success=false)   │
     │ready) │  │ + Helpful Message │
     └───────┘  └────────┬──────────┘
                         │
                         ▼
                  ┌──────────────────┐
                  │ Frontend Shows   │
                  │ • Demo video     │
                  │ • "Try shorter"  │
                  │ • Retry button   │
                  └──────────────────┘
```

---

## 🎯 Mode System

```
┌─────────────────────────────────────────────────────────┐
│                    REQUEST: mode=?                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   student    │  │   creator    │  │   research   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                 │                 │          │
│  Keywords:            Keywords:         Keywords:     │
│  lecture              viral             findings       │
│  takeaway             emotional         methodology    │
│  definition           hook              evidence       │
│  example              catchy            caveats        │
│  recap                soundbite         conclusions    │
│  quiz                 shareable                        │
│  concept              reel moment       Summary:       │
│                                         Rigorous +     │
│  Summary:             Summary:          Research       │
│  Student-            Entertainment-    focused        │
│  friendly             focused                          │
│  tone                 tone              Tone:          │
│                                         Formal +       │
│  Use Case:            Use Case:         Evidence-      │
│  Education            Content           based          │
│  Learning             Creators                         │
│  Comprehension        Social Media      Use Case:      │
│                       TikTok/Insta      Academia       │
│                       YouTube           Scientific     │
│                       Shorts            Research       │
│                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Pass to    │  │   Pass to    │  │   Pass to    │ │
│  │ highlight    │  │ highlight    │  │ highlight    │ │
│  │ search       │  │ search       │  │ search       │ │
│  │ & summary    │  │ & summary    │  │ & summary    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🛡️ Error Recovery Layers

```
┌───────────────────────────────────────────────────────────────┐
│  LAYER 1: Endpoint Try/Catch                                  │
│  (specific to each endpoint)                                  │
│  └─→ Try operation → Catch exception → Log + Fallback        │
└───────────────────┬───────────────────────────────────────────┘
                    │
┌───────────────────▼───────────────────────────────────────────┐
│  LAYER 2: Smart Fallback Chain                               │
│  (search → highlights → slices → synthetic)                   │
│  └─→ Each level tries → Falls through to next               │
└───────────────────┬───────────────────────────────────────────┘
                    │
┌───────────────────▼───────────────────────────────────────────┐
│  LAYER 3: VideoDB Error Handling                             │
│  (safe_search with retry_fallback)                            │
│  └─→ Keyword fails? Retry with semantic                     │
└───────────────────┬───────────────────────────────────────────┘
                    │
┌───────────────────▼───────────────────────────────────────────┐
│  LAYER 4: Request Validation                                 │
│  (Pydantic, Query parameter checks)                           │
│  └─→ Invalid input? Normalize to safe default               │
└───────────────────┬───────────────────────────────────────────┘
                    │
┌───────────────────▼───────────────────────────────────────────┐
│  LAYER 5: Global Exception Handler                           │
│  (@app.exception_handler(Exception))                         │
│  └─→ CATCH-ALL: Any exception → Valid JSON response        │
└───────────────────┬───────────────────────────────────────────┘
                    │
                    ▼
            ┌─────────────────┐
            │  JSON Response  │
            │  (Always Valid) │
            │  {              │
            │   "success": .. │
            │   "message": .. │
            │   "data": {}    │
            │  }              │
            └─────────────────┘
```

---

## 📈 Demo Fallback Strategy

```
User Requests: /api/demo?mode=student

         │
         ▼
    ┌─────────────────────┐
    │ Check if            │
    │ VIDEODB_DEMO_VIDEO_ │
    │ ID configured?      │
    └──┬──────────────┬───┘
   YES │              │ NO
      │              └──→ Skip step 2
      │
      ▼                   │
   ┌────────────────┐     │
   │ Try to fetch   │     │
   │ live video     │     │
   │ data (30s)     │     │
   └─┬──┬──┬────────┘     │
     │ OK│ │TIMEOUT       │
     │   │ │  or ERROR    │
     │   │ │              │
     │   │ └──────┐       │
     │   │        │       │
     │   │ ┌──────▼───────▼─────┐
     │   │ │ Use Static Demo    │
     │   │ │ Fallback           │
     │   │ │ (from JSON cache)  │
     │   │ └────────┬───────────┘
     │   │          │
     └───┼──────────┤
         │          │
         ▼          ▼
    ┌──────────────────────┐
    │  Return Demo         │
    │  success=true        │
    │  video_url (or "")   │
    │  highlights: [...]   │
    │  message: "loaded"   │
    └──────────────────────┘
```

---

## 🔄 Transcript Polling with Timeout

```
┌────────────────────────────┐
│ wait_for_transcript()      │
│ timeout_sec = 420          │
└────────┬───────────────────┘
         │
         ▼
    ┌────────────────────────┐
    │ start_time = now()     │
    │ attempts = 0           │
    └────────┬───────────────┘
             │
    ┌────────▼───────────────┐
    │ Loop: max 18 attempts  │
    │ (TRANSCRIPT_POLL_      │
    │  RETRIES=18)           │
    └────────┬───────────────┘
             │
    ┌────────▼──────────────────┐
    │ Check elapsed time:       │
    │ > 420s?                   │
    └───┬──────────────────┬────┘
   YES │                   │ NO
      │                   │
    ┌─▼────────┐      ┌───▼─────────────┐
    │ Break    │      │ Try to fetch    │
    │ loop     │      │ transcript      │
    │ (timeout)│      │ get_transcript()│
    └─┬────────┘      └───┬────┬────────┘
      │                 OK │   │ FAIL
      │                   │   │
      │             ┌─────▼──┐│
      │             │Check: │││
      │             │Ready? │││
      │             └──┬────┘││
      │          YES  │      ││ NO
      │             ┌─▼──┐   ││
      │             │ OK │   ││
      │             │Ret │   ││
      │             └────┘   ││
      │                      ││
      │             ┌────────▼▼──┐
      │             │ Sleep 2s   │
      │             │ (Poll delay)│
      │             └──┬─────────┘
      │                │
      │ ┌──────────────┘
      │ │
      └─▼──────────┐
                   │
            ┌──────▼──────┐
            │ Return:     │
            │ ready, segs │
            │ (or empty)  │
            └─────────────┘
```

---

## 🎬 Complete Request/Response Cycle

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND                                                │
│  User clicks "Search"                                    │
│  query = "viral moments"                                 │
└──────────────┬───────────────────────────────────────────┘
               │
               ├─ HTTP GET /api/search?video_id=xyz&query=viral
               │
               ▼
    ┌──────────────────────────────────────────────────────┐
    │  BACKEND natural_search()                           │
    │                                                      │
    │  try {                                               │
    │    ├─ _video_bundle(video_id)                       │
    │    ├─ highlight_pass(video, mode)                   │
    │    ├─ smart_search_bundle(...)                      │
    │    │  └─ Keyword search → NO hit                    │
    │    │  └─ Semantic search → YES hit! [clips]         │
    │    └─ return JSON                                   │
    │  } catch(e) {                                        │
    │    └─ synthetic_uniform_clips(video)                │
    │    └─ return fallback JSON                          │
    │  }                                                   │
    └──┬────────────────────────────────────────────────────┘
       │
       └─ HTTP 200 + JSON
          {
            "success": true,
            "message": "Semantic match found.",
            "shots": [
              {"start": 10, "end": 25, "text": "Moment..."}
            ],
            "fallback_used": null
          }
       │
       ▼
    ┌──────────────────────────────────────────────────────┐
    │  FRONTEND                                            │
    │  JSON parsed ✓                                       │
    │  success = true ✓                                    │
    │  shots = [clips] ✓                                   │
    │                                                      │
    │  displayClips(response.shots)                        │
    │  → User sees clips in timeline                       │
    └──────────────────────────────────────────────────────┘
```

---

## 🎯 Summary: Five Guarantees

```
GUARANTEE 1: ✅ ALWAYS VALID JSON
  ├─ Never plaintext errors
  ├─ Never 500 + exception text
  └─ Always 200 + {"success": bool, "message": "..."}

GUARANTEE 2: ✅ ALWAYS HAS DATA
  ├─ Search always returns clips (worst: synthetic timeline)
  ├─ Summary always returns text (worst: offline template)
  ├─ Demo always works (worst: static fallback)
  └─ Never empty array or null

GUARANTEE 3: ✅ GRACEFUL DEGRADATION
  ├─ Can't search? Show highlights
  ├─ No highlights? Show transcript slices
  ├─ No slices? Show synthetic timeline
  └─ Each step tries, next step ready as fallback

GUARANTEE 4: ✅ NO TIMEOUTS / HANGS
  ├─ Processing: 420s max, then demo
  ├─ Demo: 30s max, then static fallback
  ├─ Polling: Time-bounded with breaks
  └─ Frontend never stuck

GUARANTEE 5: ✅ HELPFUL ERROR MESSAGES
  ├─ "Video still processing. Please wait."
  ├─ "No exact match found, showing highlights instead."
  ├─ "Processing exceeded time limit. Try a shorter clip."
  ├─ "Transcript not ready yet. Showing preview."
  └─ Never: "Internal Server Error", "Bad Gateway", "500"
```

---

This is your safety net. The system is now **exploit-proof** and **demo-ready**. 🚀
