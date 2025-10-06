# Fix: `ffmpeg` “Invalid data” when recording CHZZK streams

This document tells **Gemini CLI** exactly how to fix the current project so recording works reliably.  
Root cause: the **temporary cookies file is deleted too early**, so `yt-dlp`/`ffmpeg` sometimes requests the HLS without auth headers and gets HTML/403 instead → `Invalid data found when processing input`.

---

## ✅ What to change (TL;DR)

1. **Do not delete the cookies file right after spawning `yt-dlp`.**  
   Instead, **keep the file for the whole recording** and delete it when the recording process is terminated.
2. Add **CHZZK-required headers** to `yt-dlp`: `Referer`, `Origin`, `User-Agent`.
3. Temporarily **disable `--hls-use-mpegts`** and test (LL‑HLS/fMP4 can conflict). Toggle back if needed.
4. Wire `watcher.py` to store and clean up the per-recording `cookie_file` alongside the process.

---

## File map

- `config/session.json` – saved Playwright cookies.
- `recorder.py` – spawns `yt-dlp` to download the HLS stream.
- `watcher.py` – polls live status and starts/stops recordings.

---

## Step 1 — Patch `recorder.py`

### 1-1. Keep cookies file for the duration of the recording

- **Before (problem):** `create_cookies_file()` writes a Netscape cookies file from `session.json`.  
  `start_recording()` runs `yt-dlp` and **immediately deletes** the cookies file in a `finally` block.
- **After (fix):** Do **not** delete it here. Return the path to `watcher.py` so it can be deleted when the process ends.

> Search in `recorder.py` for `start_recording(` and **remove** the deletion of the cookie file in any `finally:` block.  
> Then make the function **return a dict** containing the `process` and `cookie_file`.

#### Unified diff (apply conceptually if lines differ)

```diff
--- a/recorder.py
+++ b/recorder.py
@@
-def start_recording(live_details, config):
+def start_recording(live_details, config):
@@
-    try:
-        process = subprocess.Popen(command, stdout=stdout_log, stderr=stderr_log)
-        return process
-    finally:
-        if cookie_filepath and os.path.exists(cookie_filepath):
-            os.remove(cookie_filepath)
+    process = subprocess.Popen(command, stdout=stdout_log, stderr=stderr_log)
+    # Do NOT delete cookie file here. We keep it until the recording stops.
+    return {"process": process, "cookie_file": cookie_filepath}
```

### 1-2. Add CHZZK-friendly headers to `yt-dlp` command

Append these arguments when building `command`:

```python
command += [
    "--referer", "https://chzzk.naver.com/",
    "--add-header", "Origin: https://chzzk.naver.com",
    "--add-header", "User-Agent: Mozilla/5.0",
]
```

### 1-3. Temporarily drop `--hls-use-mpegts` during testing

- Comment-out or remove `--hls-use-mpegts` first.
- If testing later shows you need it, you can restore it.

Example (conceptual):

```diff
-    "--hls-use-mpegts",
+    # "--hls-use-mpegts",  # try disabled first; re‑enable if required
```

> (Optional) You can experiment with `--hls-prefer-native` vs `--hls-prefer-ffmpeg` if needed.

---

## Step 2 — Patch `watcher.py`

We must store the per-recording `cookie_file` and delete it **after** the process exits.

### 2-1. Track `cookie_file`

- Currently `currently_recording[channel_id] = {"process": Popen, "channel_name": ...}`
- Change it to also store `"cookie_file"`.

When starting a recording:

```diff
- proc = recorder.start_recording(live_details, config)
- if proc:
-     currently_recording[channel_id] = {"process": proc, "channel_name": live_details.get("channelName")}
+ started = recorder.start_recording(live_details, config)
+ if started and started.get("process"):
+     currently_recording[channel_id] = {
+         "process": started["process"],
+         "cookie_file": started.get("cookie_file"),
+         "channel_name": live_details.get("channelName"),
+     }
```

### 2-2. Delete the cookies file when stopping the recording

Where you stop a process (e.g., channel went offline or a replacement start), after killing the process add:

```python
cookie_file = info.get("cookie_file")
if cookie_file and os.path.exists(cookie_file):
    try:
        os.remove(cookie_file)
    except Exception as e:
        print(f"[warn] failed to remove cookie file {cookie_file}: {e}")
```

Make sure `import os` is present at the top of `watcher.py`.

> Keep existing Windows `taskkill` logic. If you want cross‑platform later, you can detect OS and use `.terminate()`/`os.kill` on POSIX.

---

## Step 3 — Sanity tests

Run from project root (same place as `watcher.py`).

### 3-1. Dry-run: get a live channel’s m3u8 and probe

1) Confirm live details work (your existing API code):
```
python chzzk_api.py
```
2) Using any logged m3u8 from the printout, try a verbose dump:
```
yt-dlp -v --dump-pages "<M3U8_URL>" --referer "https://chzzk.naver.com/" --add-header "Origin: https://chzzk.naver.com" --add-header "User-Agent: Mozilla/5.0"
```
- **Pass criteria:** No HTML/403 in dump; you see HLS playlists with `#EXTM3U` / `#EXT-X-...` lines.

### 3-2. Full flow

```
python watcher.py
```
- Expected:
  - When a followed channel goes live, recording starts.
  - The per-recording `cookies.txt` file **remains present** while recording.
  - On stop, process is killed and the `cookies.txt` file is deleted by `watcher.py`.

### 3-3. If it still fails

- Toggle these one by one and retry:
  - Re‑enable `--hls-use-mpegts`.
  - Try `--hls-prefer-native` or `--hls-prefer-ffmpeg`.
- Inspect last lines of `logs/*stderr.log`. If you see **HTTP/403/301/302** or **HTML**, it’s still an auth/headers issue.

---

## Step 4 — Minimal acceptance checklist

- [ ] Recording starts successfully with at least one live channel.
- [ ] No `Invalid data found when processing input` in new runs.
- [ ] Cookies file is **not** deleted until the recording is stopped.
- [ ] On stop, process and cookies file are both cleaned up.
- [ ] (Optional) Works after multiple start/stop cycles without leaks.

---

## Notes (why this fixes it)

- `yt-dlp --cookies FILE` reads the file from disk **when it needs it**. If we delete the file too early, first requests may miss cookies and get HTML/403 from CDN, which `ffmpeg` then calls “Invalid data”.
- Adding `Referer/Origin/UA` matches how browsers reach CHZZK, improving acceptance by their edge/CDN.
- Disabling `--hls-use-mpegts` helps if the live uses LL‑HLS/fMP4; you can later choose the best combo for your ffmpeg build.

---

## Optional cleanups (later)

- Cross‑platform process termination.
- Move the extra headers to `config.json` toggles if you want to control behavior without editing code.
- On startup, delete stale `cookies_*.txt` older than N hours to avoid clutter.

---

**That’s it.** Apply the changes, then run `watcher.py` and verify the checklist.
