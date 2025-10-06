# CHZZK HLS (CMAF/fMP4) Fix — Stop Forcing `.ts`, Prefer Native HLS, Ensure Segment Headers

You just ran the manual test and got:

- m3u8 **successfully fetched** ✅
- ffmpeg **fails on the first segment** with “Invalid data found when processing input” ❌
- Segment URLs end with **`.m4s` (init)** and **`.m4v` (media)** → **CMAF/fMP4-style HLS**.

This is *not* “generic ffmpeg incompatibility.” It’s our pipeline misconfigured for **fMP4 segments** and/or **segment requests missing headers**. Two surgical fixes solve it.

---

## TL;DR — Apply both

1) **Do not force TS output**. Let yt‑dlp pick the extension (usually `mp4` for fMP4).  
2) **Prefer yt‑dlp’s native HLS downloader** so Python handles all HTTP (with cookies/headers) instead of ffmpeg.

> If you *must* use ffmpeg for downloading segments, also pass headers to ffmpeg explicitly via `--downloader-args` (fallback below).

---

## Why the last run failed (reading your log)

- The playlist is normal: `#EXTM3U`, `#EXT-X-VERSION:7`, daterange lines, etc.
- Segments are **`.m4s` / `.m4v`** (CMAF/fMP4). Forcing `--hls-use-mpegts` or writing to `*.ts` is brittle here.
- ffmpeg opens the init/media URLs but **first media fetch yields invalid data** → usually **wrong container target or missing headers** during **segment** fetch (m3u8 worked, so cookies *are* fine for the playlist).

---

## Patch 1 — Recorder: stop forcing TS, prefer native HLS

### 1-1. Output template: use `%(ext)s` instead of hard-coded `.ts`

In `recorder.py` `start_recording()` where you build `output_path`, change to something like:

```python
# BEFORE (example)
# output_path = os.path.join("recordings", f"{basename}.ts")

# AFTER
output_template = os.path.join("recordings", f"{basename}.%(ext)s")
```

And pass it to yt-dlp with `-o`, as you already do.

### 1-2. Prefer native HLS

When building `command` for yt-dlp, **add**:

```python
command += ["--hls-prefer-native"]
```

**Keep** the `--cookies`, `--referer`, `--add-header Origin`, `--add-header User-Agent` you already added.

> Native HLS means yt‑dlp (Python) downloads each segment with the same cookies/headers it used for the m3u8, then remuxes. This avoids ffmpeg’s picky behavior on LL‑HLS/CMAF and mismatched headers on segments.

### 1-3. Do not delete the cookies file immediately

You already fixed this. Keep the cookies file alive for the whole recording and delete it only when the process ends (from `watcher.py`).

---

## Patch 2 — Watcher: unchanged behavior, just cleanup cookies on stop

If you haven’t yet: store `cookie_file` in `currently_recording[channel_id]` and delete it after killing the process.

```python
cookie_file = info.get("cookie_file")
if cookie_file and os.path.exists(cookie_file):
    try: os.remove(cookie_file)
    except Exception as e: print(f"[warn] cookie cleanup failed: {e}")
```

---

## Fallback (only if still failing): pass headers directly to ffmpeg

If you insist on ffmpeg for segment downloads, **also** send headers to ffmpeg via `--downloader-args` so segment requests include cookies/Referer/Origin/UA.

1) Build a single header block (Python side):

```python
cookie_header = "Cookie: " + "; ".join([f"{c['name']}={c['value']}" for c in cookies])
headers_block = (
    cookie_header + "\r\n"
    "Referer: https://chzzk.naver.com/\r\n"
    "Origin: https://chzzk.naver.com\r\n"
    "User-Agent: Mozilla/5.0"
)
```

2) In the yt‑dlp command, add:

```python
command += [
    "--downloader", "ffmpeg",
    "--downloader-args", f"ffmpeg_i:-headers {headers_block!r}",
]
```

> Note: `ffmpeg_i:` applies to the *input* side. Keep `--cookies` too if you like; the explicit `-headers` ensures ffmpeg always sends the cookies/headers on **segment** requests.

---

## Minimal manual test commands

From *inside* the same environment:

### A) Native HLS (recommended)

```bash
yt-dlp --no-part   --cookies /tmp/tmpzso279ud   --hls-prefer-native   --referer "https://chzzk.naver.com/"   --add-header "Origin: https://chzzk.naver.com"   --add-header "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"   -o "recordings/manual_test_output.%(ext)s"   "<M3U8_URL>"
```

**Pass criteria:** it starts writing `manual_test_output.mp4` (or similar), no “Invalid data” anywhere.

### B) ffmpeg downloader with explicit headers (fallback)

```bash
yt-dlp --no-part   --cookies /tmp/tmpzso279ud   --downloader ffmpeg   --downloader-args "ffmpeg_i:-headers 'Cookie: <name=val; ...>
Referer: https://chzzk.naver.com/
Origin: https://chzzk.naver.com
User-Agent: Mozilla/5.0'"   -o "recordings/manual_test_output.%(ext)s"   "<M3U8_URL>"
```

> Replace the cookie string with actual cookies if testing by hand. In code, auto‑generate from `session.json` as shown above.

---

## Acceptance checklist

- [ ] Recording runs with **`--hls-prefer-native`** and produces `*.mp4` (or similar), no ffmpeg segment errors.
- [ ] If you want `*.ts`, only enable `--hls-use-mpegts` when the playlist is MPEG‑TS (not CMAF/fMP4). Auto-detect later if needed.
- [ ] Cookie file persists during recording and is cleaned on stop.
- [ ] Repeated start/stop cycles leave no zombie processes or stale cookies.

---

## Why Gemini’s “ffmpeg incompatible” speech is misleading

- Your log proves cookies/headers are good **for the playlist** and the CDN is reachable. The failure is at **segment** reads of **fMP4**.  
- Using **native HLS** (Python HTTP) removes ffmpeg from the download path → no segment header mismatch, no CMAF quirks.  
- Modern ffmpeg can read CMAF just fine *if* headers are correct and container is not forcibly set to TS. The blanket “ffmpeg is incompatible” conclusion is premature.

---

**Do these two things first:** (1) stop forcing `.ts`, (2) add `--hls-prefer-native`.  
This resolves the class of failures your last log shows.
