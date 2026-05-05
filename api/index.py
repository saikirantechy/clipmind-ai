"""VidAI — 100% stable, hackathon-ready FastAPI + VideoDB backend."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

PROCESS_TIMEOUT_SEC = int(os.getenv("VIDEODB_PROCESS_TIMEOUT_SEC", "420"))
TRANSCRIPT_POLL_RETRIES = int(os.getenv("VIDEODB_TRANSCRIPT_RETRIES", "18"))
TRANSCRIPT_POLL_DELAY = float(os.getenv("VIDEODB_TRANSCRIPT_DELAY_SEC", "2"))
SEARCH_KIND_PRIORITY = ["keyword", "semantic"]  # Try keyword first, fall back to semantic

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("vidai")

FRONT_SNIPPET = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "demo-offline-snippet.json")
)


def normalize_mode(mode: str | None) -> str:
    m = (mode or "student").strip().lower()
    if m in ("student", "creator", "research"):
        return m
    return "student"


def mode_config(mode: str) -> tuple[str, str]:
    """highlights_prompt, summary_voice"""
    m = normalize_mode(mode)
    if m == "creator":
        return (
            "viral emotional hook peak catchy soundbite shareable reel moment",
            "Assume a short-form creator audience.",
        )
    if m == "research":
        return (
            "findings methodology evidence caveats conclusions implications",
            "Assume rigorous research intake with evidence and caveats.",
        )
    return (
        "lecture takeaway definition example recap quiz concept explanation",
        "Assume an education / student-friendly recap tone.",
    )


def _api_key() -> str | None:
    return os.getenv("VIDEODB_API_KEY") or os.getenv("VIDEO_DB_API_KEY")


def connect_vdb():
    import videodb

    key = _api_key()
    if not key:
        raise RuntimeError(
            "Set VIDEODB_API_KEY (https://console.videodb.io).",
        )
    return videodb.connect(api_key=key)


def _segments_from_transcript(transcript) -> list[dict]:
    out: list[dict] = []
    if transcript is None:
        return out
    if isinstance(transcript, list):
        for row in transcript:
            if hasattr(row, "start"):
                out.append(
                    {
                        "start": float(row.start),
                        "end": float(row.end),
                        "text": getattr(row, "text", "") or "",
                    },
                )
            elif isinstance(row, dict):
                out.append(
                    {
                        "start": float(row.get("start", 0)),
                        "end": float(row.get("end", 0)),
                        "text": str(row.get("text", "")),
                    },
                )
        return out
    if hasattr(transcript, "segments"):
        try:
            for row in transcript.segments:
                out.extend(_segments_from_transcript([row]))
        except Exception:
            pass
    return out


def _serialize_shots(shots) -> list[dict]:
    rows = []
    for s in shots or []:
        rows.append(
            {
                "start": float(getattr(s, "start", 0)),
                "end": float(getattr(s, "end", 0)),
                "text": getattr(s, "text", "") or "",
            },
        )
    return rows


def transcript_length_hint(video, segments: list[dict]) -> int:
    try:
        txt = video.get_transcript_text() or ""
        return len(txt.strip())
    except Exception:
        return len(" ".join(x.get("text", "") for x in segments).strip())


def transcript_ready(video, segments: list[dict]) -> tuple[bool, str]:
    n = transcript_length_hint(video, segments)
    if n >= 20:
        return True, ""
    return False, "Video still processing. Please wait a bit and retry."


def wait_for_transcript(video, timeout_sec: int = PROCESS_TIMEOUT_SEC) -> tuple[bool, list[dict]]:
    """Poll until transcript fills or timeout reached. Always returns segments."""
    segments: list[dict] = []
    start_time = time.time()
    
    for attempt in range(TRANSCRIPT_POLL_RETRIES):
        elapsed = time.time() - start_time
        if elapsed > timeout_sec:
            log.warning("transcript poll timeout after %.1f sec", elapsed)
            break
            
        try:
            segments = _segments_from_transcript(video.get_transcript())
        except Exception as e:
            log.debug("get_transcript attempt %d failed: %s", attempt + 1, str(e)[:100])
        
        ok, _ = transcript_ready(video, segments)
        if ok:
            log.info(
                "transcript ready attempt=%d elapsed=%.1fs chars≈%d segs=%d",
                attempt + 1,
                elapsed,
                transcript_length_hint(video, segments),
                len(segments),
            )
            return True, segments
        
        log.info("transcript poll attempt=%d (%.1f sec elapsed, still short)", attempt + 1, elapsed)
        time.sleep(TRANSCRIPT_POLL_DELAY)
    
    log.warning(
        "transcript incomplete after %.1f sec, chars≈%d segs=%d (continuing with fallback)",
        time.time() - start_time,
        transcript_length_hint(video, segments),
        len(segments),
    )
    return False, segments


def safe_search(video, query: str, *, search_kind: str, retry_fallback: bool = True) -> list[dict]:
    """Search with explicit fallback chain: keyword → semantic → empty."""
    import videodb
    from videodb.exceptions import VideodbError

    q = (query or "").strip()
    if not q:
        log.debug("search: empty query")
        return []
    
    try:
        log.info("search START kind=%s q_len=%s", search_kind, len(q))
        res = video.search(q, search_type=search_kind)
        out = _serialize_shots(res.get_shots())
        log.info("search OK kind=%s n=%s", search_kind, len(out))
        return out
    except VideodbError as e:
        # "No results found" or other VideoDB errors
        log.warning("search VideodbError kind=%s: %s", search_kind, str(e)[:120])
        if retry_fallback and search_kind == "keyword":
            log.info("search retrying with semantic fallback")
            return safe_search(video, query, search_kind="semantic", retry_fallback=False)
        return []
    except Exception as e:
        log.exception("search unexpected error kind=%s: %s", search_kind, e)
        return []


def highlight_pass(video, mode: str) -> list[dict]:
    """Extract highlights using mode-specific keywords + semantic search."""
    hq, _ = mode_config(mode)
    try:
        # Try keyword first (faster), then semantic
        semantic = safe_search(video, hq, search_kind="keyword", retry_fallback=True)
        log.info("highlights extracted=%s", len(semantic))
        return semantic
    except Exception as e:
        log.exception("highlight_pass unexpected: %s", e)
        return []


def transcript_slice_fallback(segments: list[dict], n: int = 3) -> list[dict]:
    if not segments:
        return []
    out = []
    for seg in segments[:n]:
        s, e = float(seg["start"]), float(seg["end"])
        if e <= s:
            e = s + 2.5
        out.append(
            {"start": s, "end": e, "text": seg.get("text", "")[:240], "source": "transcript_slice"},
        )
    log.info("fallback transcript slices=%s", len(out))
    return out


def synthetic_uniform_clips(video, n: int = 3) -> list[dict]:
    raw_len = getattr(video, "length", None) or 180.0
    try:
        length = float(raw_len)
    except (TypeError, ValueError):
        length = 180.0
    length = max(length, 12.0)
    chunk = max(4.0, length / (n + 1))
    out = []
    for i in range(n):
        s = chunk * i
        e = min(s + chunk * 0.7, length)
        if e - s < 2:
            e = min(s + 3.0, length)
        out.append(
            {"start": s, "end": e, "text": f"[Auto segment {i + 1}]", "source": "uniform"},
        )
    log.warning("uniform synthetic clips=%s (no transcript)", len(out))
    return out


def smart_search_bundle(
    video,
    *,
    query: str,
    mode: str,
    cached_highlights: list[dict],
    transcript_segments: list[dict],
) -> dict[str, Any]:
    """
    Search fallback chain:
    1. Keyword match → return
    2. Semantic match → return
    3. Pre-computed highlights
    4. Transcript slices
    5. Synthetic uniform clips
    
    ALWAYS returns a valid result.
    """
    ready_ok, hint = transcript_ready(video, transcript_segments)
    q = query.strip()

    # If transcript not ready, return early with slices or synthetic
    if not ready_ok:
        results = transcript_slice_fallback(transcript_segments) or synthetic_uniform_clips(video)
        log.info("search: transcript not ready, returning fallback (n=%d)", len(results))
        return {
            "success": True,
            "message": hint or "Indexing not ready. Showing video segments.",
            "ready": False,
            "query": q,
            "shots": results,
            "fallback_used": "not_ready_slices",
        }

    # Transcript is ready — try actual search
    if q:
        keyword_hits = safe_search(video, q, search_kind="keyword", retry_fallback=False)
        if keyword_hits:
            log.info("search: keyword match (n=%d)", len(keyword_hits))
            return {
                "success": True,
                "message": "Exact match found.",
                "ready": True,
                "query": q,
                "shots": keyword_hits,
                "fallback_used": None,
                "search_path": "keyword",
            }

        # Try semantic
        semantic_hits = safe_search(video, q, search_kind="semantic", retry_fallback=False)
        if semantic_hits:
            log.info("search: semantic match (n=%d)", len(semantic_hits))
            return {
                "success": True,
                "message": "Semantic match found.",
                "ready": True,
                "query": q,
                "shots": semantic_hits,
                "fallback_used": None,
                "search_path": "semantic",
            }
        
        # No search hits — try highlights
        log.info("search: no matches, trying highlights")

    # Fallback 1: Pre-computed highlights
    cand = cached_highlights[:] if cached_highlights else highlight_pass(video, mode)
    if cand:
        return {
            "success": True,
            "message": (
                "No search results found. Showing curated highlights instead."
                if q
                else "Showing curated highlights."
            ),
            "ready": True,
            "query": q,
            "shots": cand,
            "fallback_used": "highlights",
        }

    # Fallback 2: Transcript slices
    cand = transcript_slice_fallback(transcript_segments, n=5)
    if cand:
        return {
            "success": True,
            "message": (
                "Showing first transcript moments."
                if q
                else "Showing transcript segments."
            ),
            "ready": True,
            "query": q,
            "shots": cand,
            "fallback_used": "transcript_slices",
        }

    # Fallback 3: Synthetic clips (should always work)
    cand = synthetic_uniform_clips(video, n=5)
    return {
        "success": True,
        "message": "Showing video timeline segments.",
        "ready": True,
        "query": q,
        "shots": cand,
        "fallback_used": "synthetic",
    }


def clip_stream(conn, coll, video_id: str, start: float, end: float) -> str:
    from videodb.editor import Clip, Timeline, Track, VideoAsset

    video = coll.get_video(video_id)
    duration = max(0.5, float(end) - float(start))
    timeline = Timeline(conn)
    track = Track()
    asset = VideoAsset(id=video.id, start=float(start))
    clip = Clip(asset=asset, duration=duration)
    track.add_clip(0, clip)
    timeline.add_track(track)
    return timeline.generate_stream()


def reel_stream(conn, coll, video_id: str, segments: list[dict]) -> str:
    from videodb.editor import Clip, Timeline, Track, VideoAsset

    video = coll.get_video(video_id)
    timeline = Timeline(conn)
    track = Track()
    t_off = 0.0
    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])
        duration = max(0.5, end - start)
        asset = VideoAsset(id=video.id, start=start)
        clip = Clip(asset=asset, duration=duration)
        track.add_clip(t_off, clip)
        t_off += duration
    timeline.add_track(track)
    return timeline.generate_stream()


def load_local_fallback_snippet() -> dict[str, Any]:
    try:
        with open(FRONT_SNIPPET, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return {}
    except json.JSONDecodeError:
        return {}


def static_demo_payload(mode: str) -> dict[str, Any]:
    snip = load_local_fallback_snippet()
    hq, _ = mode_config(mode)
    text = (
        snip.get("transcript_fallback")
        or snip.get("pitch")
        or "(Demo fallback) Configure VIDEODB_DEMO_VIDEO_ID or process a clip."
        f" Mode `{normalize_mode(mode)}` focuses on `{hq}`."
    )
    return {
        "success": True,
        "fallback": True,
        "video_id": "",
        "stream_url": "",
        "transcript_text": text,
        "transcript_segments": [],
        "highlights": [],
        "mode": normalize_mode(mode),
        "demo": True,
        "message": (
            snip.get("message")
            or "Static demo scaffold — ingest a clip or configure VIDEODB_DEMO_VIDEO_ID."
        ),
    }


def build_process_payload(video, conn, coll, *, mode: str) -> dict[str, Any]:
    _, _ = conn, coll
    try:
        stream_url = video.generate_stream()
    except Exception as e:
        log.warning("generate_stream deferred: %s", e)
        stream_url = getattr(video, "stream_url", "") or ""

    hq, _ = mode_config(mode)
    highlights = highlight_pass(video, mode)
    transcript_segments = _segments_from_transcript(video.get_transcript())
    transcript_text = ""
    try:
        transcript_text = video.get_transcript_text() or ""
    except Exception:
        transcript_text = "\n".join(s["text"] for s in transcript_segments)

    if not highlights:
        highlights = transcript_slice_fallback(transcript_segments) or synthetic_uniform_clips(
            video,
        )

    log.info(
        "process_payload video=%s transcript_chars=%s highlights=%s",
        video.id,
        len(transcript_text),
        len(highlights),
    )

    return {
        "success": True,
        "video_id": video.id,
        "name": getattr(video, "name", "") or "",
        "stream_url": stream_url,
        "transcript_text": transcript_text,
        "transcript_segments": transcript_segments,
        "highlights": highlights,
        "mode": normalize_mode(mode),
        "ready": transcript_ready(video, transcript_segments)[0],
        "message": "Processed.",
    }


def ingest_and_index_blocking(url_or_path: str, *, youtube: bool, mode: str) -> dict[str, Any]:
    """Ingest video and index (transcript, speech, etc.)."""
    conn = connect_vdb()
    coll = conn.get_collection()

    log.info(
        "ingest START youtube=%s path_len=%d mode=%s",
        youtube,
        len(url_or_path),
        mode,
    )

    try:
        if youtube:
            video = coll.upload(url=url_or_path)
        else:
            video = coll.upload(file_path=url_or_path)
    except Exception as e:
        log.exception("ingest upload failed: %s", e)
        raise

    try:
        video.generate_transcript()
    except Exception as e:
        log.warning("transcript generation failed: %s", str(e)[:100])
    
    try:
        video.index_spoken_words()
    except Exception as e:
        log.warning("speech index failed: %s", str(e)[:100])

    # Wait for transcript with timeout
    ok, segments = wait_for_transcript(video, timeout_sec=PROCESS_TIMEOUT_SEC)
    if not ok:
        log.warning("transcript incomplete after timeouts — continuing with fallbacks")

    # Ensure we have segments
    segments = segments or _segments_from_transcript(video.get_transcript())
    try:
        tr_len = transcript_length_hint(video, segments)
    except Exception:
        tr_len = 0

    log.info(
        "ingest DONE video=%s transcript_len=%d segments=%d",
        video.id,
        tr_len,
        len(segments),
    )

    return build_process_payload(video, conn, coll, mode=mode)


# --- FastAPI ---
app = FastAPI(title="VidAI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def json_ok(payload: dict[str, Any], status: int = 200):
    out = dict(payload)
    out.setdefault("success", True)
    out.setdefault("message", "ok")
    return JSONResponse(content=out, status_code=status)


def json_err(message: str, status: int = 200, **extra):
    payload = {"success": False, "message": message, **extra}
    return JSONResponse(content=payload, status_code=status)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        {"success": False, "message": detail, "data": [], "shots": []},
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception(_, exc: RequestValidationError):
    errors = [{"field": str(e.get("loc", [])), "msg": str(e.get("msg", ""))} for e in exc.errors()]
    return JSONResponse(
        {
            "success": False,
            "message": "Invalid request parameters",
            "errors": errors,
            "data": [],
        },
        status_code=422,
    )


@app.exception_handler(Exception)
async def global_exception(_, exc: Exception):
    """CRITICAL: Catch ALL exceptions. Always return valid JSON, never crash."""
    error_trace = traceback.format_exc()
    error_msg = str(exc)[:200]  # Truncate for safety
    
    log.error("UNHANDLED EXCEPTION: %s | %s", error_msg, error_trace[:300])
    
    return JSONResponse(
        {
            "success": False,
            "message": f"Internal error: {error_msg}",
            "error_type": type(exc).__name__,
            "data": [],
            "shots": [],
        },
        status_code=500,
    )


class ProcessUrlBody(BaseModel):
    url: HttpUrl
    mode: str = "student"


class SearchBody(BaseModel):
    query: str


class ReelBody(BaseModel):
    clips: list[dict]


class SummaryBody(BaseModel):
    mode: str = "student"


@app.get("/api/health")
def health():
    return json_ok(
        {
            "message": "ok",
            "videodb_api_key_present": bool(_api_key()),
            "demo_video_configured": bool(os.getenv("VIDEODB_DEMO_VIDEO_ID", "").strip()),
            "process_timeout_sec": PROCESS_TIMEOUT_SEC,
        },
    )


@app.get("/api/demo")
def load_prepared_demo(mode: str = "student"):
    """Load demo video or fallback to static scaffold."""
    mode = normalize_mode(mode)
    demo_vid = os.getenv("VIDEODB_DEMO_VIDEO_ID", "").strip()
    
    if not demo_vid:
        log.info("/api/demo no VIDEODB_DEMO_VIDEO_ID, using static fallback")
        return json_ok(static_demo_payload(mode), status=200)

    try:
        log.info("/api/demo loading video_id=%s", demo_vid[:16])
        conn = connect_vdb()
        coll = conn.get_collection()
        video = coll.get_video(demo_vid)
        
        # Wait for transcript with timeout
        ok, segments = wait_for_transcript(video, timeout_sec=30)
        if not ok:
            log.warning("/api/demo transcript incomplete, using fallbacks")
        
        transcript_text = ""
        try:
            transcript_text = video.get_transcript_text() or ""
        except Exception:
            transcript_text = "\n".join(s.get("text", "") for s in segments)

        # Try to generate stream, but don't fail if it takes too long
        stream_url = ""
        try:
            stream_url = video.generate_stream()
        except Exception as e:
            log.warning("/api/demo stream generation failed: %s", str(e)[:100])

        # Get highlights with fallbacks
        highlights = highlight_pass(video, mode)
        if not highlights:
            highlights = transcript_slice_fallback(segments, n=5) or synthetic_uniform_clips(video, n=3)

        log.info("/api/demo SUCCESS video=%s highlights=%d", demo_vid[:16], len(highlights))

        return json_ok(
            {
                "video_id": video.id,
                "name": getattr(video, "name", "") or "Demo Video",
                "stream_url": stream_url,
                "transcript_text": transcript_text[:20000],  # Limit size
                "transcript_segments": segments[:200],  # Limit array
                "highlights": highlights[:10],
                "mode": mode,
                "demo": True,
                "ready": ok,
                "message": "Demo loaded." if ok else "Demo loaded (transcript still processing).",
            },
            status=200,
        )
    
    except Exception as e:
        log.exception("/api/demo error: %s", e)
        # Fall back to static demo
        fb = static_demo_payload(mode)
        fb.update({
            "success": True,  # Still return success so UI doesn't break
            "message": f"Demo video unavailable, showing static fallback.",
        })
        return json_ok(fb, status=200)


def _timed_process(exec_fn):
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        fut = executor.submit(exec_fn)
        return fut.result(timeout=PROCESS_TIMEOUT_SEC)
    except FuturesTimeout:
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


@app.post("/api/process")
@app.post("/api/process/url")
def api_process(body: ProcessUrlBody):
    """Process video from URL (YouTube or direct link)."""
    try:
        def job():
            return ingest_and_index_blocking(str(body.url), youtube=True, mode=body.mode)

        log.info("processing URL mode=%s url_len=%d", body.mode, len(str(body.url)))
        payload = _timed_process(job)
        
        if payload is None:
            # Timeout occurred — return demo fallback with success=false
            log.warning("processing TIMEOUT after %d sec", PROCESS_TIMEOUT_SEC)
            fb = static_demo_payload(body.mode)
            fb.update({
                "success": False,
                "message": (
                    f"Processing exceeded {PROCESS_TIMEOUT_SEC}s limit. "
                    "Try a shorter clip or check API key."
                ),
            })
            return json_ok(fb, status=200)
        
        log.info("processing SUCCESS")
        return json_ok(payload, status=200)
    
    except Exception as e:
        log.exception("api_process unexpected error: %s", e)
        fb = static_demo_payload(body.mode)
        fb.update({
            "success": False,
            "message": f"Processing error: {str(e)[:100]}",
        })
        return json_ok(fb, status=200)


@app.post("/api/process/upload")
async def api_process_upload(file: UploadFile = File(...), mode: str = Form("student")):
    """Upload and process video file."""
    suffix = os.path.splitext(file.filename or "")[1] or ".mp4"
    temp_path = None
    mode = normalize_mode(mode)
    
    try:
        log.info("upload START file=%s mode=%s", file.filename or "unknown", mode)
        
        content = await file.read()
        if not content:
            return json_ok(
                {
                    **static_demo_payload(mode),
                    "success": False,
                    "message": "File is empty.",
                },
                status=200,
            )
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            temp_path = tmp.name

        def job():
            return ingest_and_index_blocking(temp_path, youtube=False, mode=mode)

        payload = _timed_process(job)
        if payload is None:
            log.warning("upload TIMEOUT after %d sec", PROCESS_TIMEOUT_SEC)
            return json_ok(
                {
                    **static_demo_payload(mode),
                    "success": False,
                    "message": (
                        f"Processing exceeded {PROCESS_TIMEOUT_SEC}s limit. "
                        "Try a shorter video."
                    ),
                },
                status=200,
            )
        
        log.info("upload SUCCESS")
        return json_ok(payload, status=200)
    
    except Exception as e:
        log.exception("upload failed: %s", e)
        return json_ok(
            {
                **static_demo_payload(mode),
                "success": False,
                "message": f"Upload failed: {str(e)[:80]}",
            },
            status=200,
        )
    
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                log.debug("temp file cleanup failed: %s", temp_path)


def _video_bundle(video_id: str):
    conn = connect_vdb()
    coll = conn.get_collection()
    video = coll.get_video(video_id)
    segments = _segments_from_transcript(video.get_transcript())
    return conn, coll, video, segments


@app.post("/api/videos/{video_id}/search")
def natural_search(video_id: str, body: SearchBody, mode: str = Query("student")):
    """Search within video. Always returns valid result."""
    try:
        mode = normalize_mode(mode)
        log.info("search POST video=%s query_len=%d mode=%s", video_id[:16], len(body.query), mode)
        
        _, _, video, transcript_segments = _video_bundle(video_id)
        cached = highlight_pass(video, mode)

        bundle = smart_search_bundle(
            video,
            query=body.query,
            mode=mode,
            cached_highlights=cached,
            transcript_segments=transcript_segments or _segments_from_transcript(video.get_transcript()),
        )
        
        log.info("search result shots=%d fallback=%s", len(bundle.get("shots", [])), bundle.get("fallback_used"))
        return json_ok(bundle, status=200)
    
    except Exception as e:
        log.exception("search failed: %s", e)
        # Final fallback: return synthetic clips
        try:
            _, _, vid, segments = _video_bundle(video_id)
            shots = synthetic_uniform_clips(vid, n=3)
        except Exception:
            shots = []
        
        return json_ok(
            {
                "success": True,
                "message": f"Search error handled gracefully.",
                "ready": False,
                "query": body.query.strip(),
                "shots": shots,
                "fallback_used": "error_recovery",
            },
            status=200,
        )


@app.get("/api/search")
def unified_search_get(
    video_id: str = Query(..., min_length=1),
    q: str = Query("", alias="query"),
    mode: str = Query("student"),
):
    q = q.strip()
    stub = SearchBody(query=q if q else " ")
    return natural_search(video_id, stub, mode)


def _reel_candidates(video, mode: str, segments: list[dict]) -> list[dict]:
    cand = highlight_pass(video, mode)
    if cand:
        return cand[:8]
    cand = transcript_slice_fallback(segments, n=8)
    if cand:
        return cand
    return synthetic_uniform_clips(video, n=min(8, 3))


@app.get("/api/reel")
def reel_get(video_id: str = Query(..., min_length=1), mode: str = Query("student")):
    """Generate reel from highlights or fallback clips."""
    try:
        mode = normalize_mode(mode)
        log.info("reel GET video=%s mode=%s", video_id[:16], mode)
        
        conn, coll, video, segments = _video_bundle(video_id)
        clips = _reel_candidates(video, mode, segments)
        
        if not clips:
            log.warning("reel: no clips available")
            return json_ok(
                {
                    "success": False,
                    "stream_url": "",
                    "message": "No clips available for reel.",
                    "clips": [],
                },
                status=200,
            )
        
        stream_url = reel_stream(conn, coll, video_id, clips[:8])
        log.info("reel generated clips=%d", len(clips))
        
        return json_ok(
            {
                "success": True,
                "stream_url": stream_url,
                "clips": clips[:8],
                "message": "Reel compiled successfully.",
            },
            status=200,
        )
    
    except Exception as e:
        log.exception("reel failed: %s", e)
        return json_ok(
            {
                "success": False,
                "stream_url": "",
                "message": f"Reel generation failed: {str(e)[:80]}",
                "clips": [],
            },
            status=200,
        )


def build_summary(coll, video, mode: str) -> tuple[str, str]:
    _, profile = mode_config(mode)
    text = ""
    try:
        text = (video.get_transcript_text() or "")[:12000]
    except Exception:
        text = ""

    try:
        r = coll.generate_text(
            prompt=(
                profile
                + "From this transcript ONLY, respond with Markdown using exactly these headings:\n"
                "## Bullet notes\n- five crisp bullets\n"
                "## Key takeaways\n"
                "- three sentences max\n"
                "## What you learned\n"
                "- one short paragraph\n\n"
                "Ground every claim in transcript. "
                "If unsure, write Unstated.\n\n---\nTRANSCRIPT:\n"
                + text
            ),
            model_name="pro",
            response_type="text",
        )
        bullets = str(r).strip()
        msg = "Summary generated."
    except Exception:
        excerpt = text[:900]
        bullets = (
            "## Bullet notes\n"
            "- Transcript excerpts below remain searchable.\n"
            "- Highlights and reels still work offline of this AI pass.\n"
            "- Rotate API credits or simplify prompt if quotas hit.\n"
            "## Key takeaways\n"
            "- Core story lives in searchable transcript.\n"
            "## What you learned\n"
            "- VidAI keeps streaming even when text-generation soft-fails.\n\n"
            f"(Transcript excerpt) {excerpt}"
        )
        msg = "Summary used offline template (VideoDB text-gen unavailable)."
    return bullets, msg


@app.get("/api/summary")
def summary_get(video_id: str = Query(..., min_length=1), mode: str = Query("student")):
    """Generate AI summary or fallback template."""
    try:
        mode = normalize_mode(mode)
        log.info("summary GET video=%s mode=%s", video_id[:16], mode)
        
        conn, coll, video, segments = _video_bundle(video_id)
        ready_ok, hint = transcript_ready(video, segments)
        
        if not ready_ok:
            log.info("summary: transcript not ready")
            return json_ok(
                {
                    "success": False,
                    "message": hint or "Transcript still processing.",
                    "bullets": "",
                    "mode": mode,
                    "ready": False,
                },
                status=200,
            )
        
        bullets, msg = build_summary(coll, video, mode)
        log.info("summary generated len=%d", len(bullets))
        
        return json_ok(
            {
                "success": True,
                "bullets": bullets,
                "mode": mode,
                "ready": True,
                "message": msg,
            },
            status=200,
        )
    
    except Exception as e:
        log.exception("summary GET failed: %s", e)
        return json_ok(
            {
                "success": False,
                "message": f"Summary error: {str(e)[:80]}",
                "bullets": "Unable to generate summary at this time.",
                "mode": normalize_mode(mode),
                "ready": False,
            },
            status=200,
        )


@app.post("/api/videos/{video_id}/summary")
def api_summary_post(video_id: str, body: SummaryBody):
    """Generate AI summary or fallback template."""
    try:
        mode = normalize_mode(body.mode)
        log.info("summary POST video=%s mode=%s", video_id[:16], mode)
        
        conn, coll, video, segments = _video_bundle(video_id)
        ready_ok, hint = transcript_ready(video, segments)
        
        if not ready_ok:
            log.info("summary POST: transcript not ready")
            return json_ok(
                {
                    "success": False,
                    "message": hint or "Transcript still processing.",
                    "bullets": "",
                    "mode": mode,
                    "ready": False,
                },
                status=200,
            )
        
        bullets, msg = build_summary(coll, video, mode)
        log.info("summary POST generated len=%d", len(bullets))
        
        return json_ok(
            {
                "success": True,
                "bullets": bullets,
                "mode": mode,
                "ready": True,
                "message": msg,
            },
            status=200,
        )
    
    except Exception as e:
        log.exception("summary POST failed: %s", e)
        return json_ok(
            {
                "success": False,
                "message": f"Summary error: {str(e)[:80]}",
                "bullets": "Unable to generate summary at this time.",
                "mode": normalize_mode(body.mode),
                "ready": False,
            },
            status=200,
        )


@app.get("/api/videos/{video_id}/subtitles-stream")
def subtitles_stream(video_id: str):
    """Generate subtitle stream."""
    try:
        log.info("subtitles GET video=%s", video_id[:16])
        _, _, video, _ = _video_bundle(video_id)
        stream_url = video.add_subtitle()
        
        return json_ok(
            {
                "success": True,
                "stream_url": stream_url,
                "message": "Subtitle stream ready.",
            },
            status=200,
        )
    except Exception as e:
        log.warning("subtitles failed: %s", str(e)[:100])
        return json_ok(
            {
                "success": False,
                "stream_url": "",
                "message": f"Subtitles unavailable: {str(e)[:80]}",
            },
            status=200,
        )


@app.get("/api/videos/{video_id}/clip-stream")
def single_clip(video_id: str, start: float = Query(...), end: float = Query(...)):
    """Generate single clip stream."""
    try:
        log.info("clip GET video=%s start=%.1f end=%.1f", video_id[:16], start, end)
        conn, coll, _, _ = _video_bundle(video_id)
        
        # Validate range
        start = max(0.0, float(start))
        end = max(start + 0.5, float(end))
        
        stream_url = clip_stream(conn, coll, video_id, start, end)
        
        return json_ok(
            {
                "success": True,
                "stream_url": stream_url,
                "message": "Clip compiled.",
            },
            status=200,
        )
    except Exception as e:
        log.exception("clip stream failed: %s", e)
        return json_ok(
            {
                "success": False,
                "stream_url": "",
                "message": f"Clip generation failed: {str(e)[:80]}",
            },
            status=200,
        )


@app.post("/api/videos/{video_id}/reel")
def make_reel(video_id: str, body: ReelBody):
    """Generate custom reel from provided clips."""
    try:
        if not body.clips:
            log.warning("reel POST: no clips provided")
            return json_ok(
                {
                    "success": False,
                    "stream_url": "",
                    "message": "clips array required",
                    "clips": [],
                },
                status=200,
            )
        
        log.info("reel POST video=%s clips=%d", video_id[:16], len(body.clips))
        conn, coll, _, _ = _video_bundle(video_id)
        stream_url = reel_stream(conn, coll, video_id, body.clips[:12])
        
        return json_ok(
            {
                "success": True,
                "stream_url": stream_url,
                "clips": body.clips[:12],
                "message": "Reel compiled successfully.",
            },
            status=200,
        )
    
    except Exception as e:
        log.warning("reel POST failed: %s", str(e)[:100])
        return json_ok(
            {
                "success": False,
                "stream_url": "",
                "message": f"Reel generation failed: {str(e)[:80]}",
                "clips": body.clips if body.clips else [],
            },
            status=200,
        )


FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")