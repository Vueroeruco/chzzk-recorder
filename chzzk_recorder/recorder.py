#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure‑Python LL‑HLS/HLS recorder — drop‑in replacement for the old ffmpeg wrapper.

- Public API kept identical: start_recording(live_details, config=None)
- Returns: {"process": <shim>, "output": path, "channel": ..., "title": ..., "timestamp": ...}
- Uses a browser‑like single session with LL‑HLS support (_HLS_msn/_HLS_part), stall detection, and light prefetch.
- Can roll files by time (segment_seconds) like segmented TS.

Requires: aiohttp
"""

import asyncio
import json
import os
import re
import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from urllib.parse import urljoin, urlencode, urlparse, urlunparse, parse_qsl

import aiohttp

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
CHZZK_ORIGIN = "https://chzzk.naver.com"

# ================= Helpers =================

def _sanitize_name(name: str) -> str:
    if not name:
        return "unknown"
    return re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ _]", "", name).strip() or "unknown"


def _now_ts() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _with_params(url: str, extra: Dict[str, str]) -> str:
    u = urlparse(url)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    q.update(extra)
    return urlunparse(u._replace(query=urlencode(q)))


# -------- tiny playlist parsing --------

def _parse_master_variants(text: str, base_url: str) -> List[str]:
    urls: List[str] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        if ln.endswith('.m3u8'):
            urls.append(urljoin(base_url, ln))
    return urls


def _choose_1080p(urls: List[str]) -> Optional[str]:
    for u in urls:
        if "1080" in u or "1080p" in u:
            return u
    return urls[-1] if urls else None


def _parse_media_playlist(text: str) -> Tuple[Optional[int], List[str]]:
    msn = None
    uris: List[str] = []
    for ln in text.splitlines():
        if ln.startswith('#EXT-X-MEDIA-SEQUENCE'):
            try:
                msn = int(ln.split(':', 1)[1].strip())
            except Exception:
                pass
        elif ln and not ln.startswith('#'):
            uris.append(ln.strip())
    return msn, uris


# -------- process shim to mimic Popen API --------
class _RecorderProcess:
    def __init__(self, stop_cb, desc: str):
        self._stop_cb = stop_cb
        self._returncode: Optional[int] = None
        self._desc = desc

    def terminate(self):
        self._returncode = 0
        self._stop_cb()

    def kill(self):
        self.terminate()

    def poll(self):
        return self._returncode

    def wait(self, timeout: Optional[float] = None):
        return self._returncode

    @property
    def pid(self):
        return None

    def __repr__(self):
        return f"<_RecorderProcess {self._desc}>"


# ================= Core recorder =================
@dataclass
class _Cfg:
    session_path: str
    out_path: str
    quality_prefer_1080: bool = True
    llhls: bool = True
    prefetch: int = 2
    stall_seconds: int = 15
    timeout_playlist: int = 10
    timeout_media: int = 6
    live_edge_bias: int = 2
    segment_seconds: int = int(os.getenv("SEGMENT_SECONDS", "0"))  # 0=single file


class _LLHLSRecorder:
    def __init__(self, m3u8_url: str, cfg: _Cfg, log_dir: Path):
        self.m3u8_url = m3u8_url
        self.cfg = cfg
        self.log_dir = log_dir
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_file = None
        self.cur_file_path: Optional[Path] = None
        self.started_time = 0.0
        self.last_size = 0
        self.idle = 0
        self.cur_msn = 0
        self.cur_part = 0
        self.stop = False

    async def _create_session(self) -> aiohttp.ClientSession:
        cookies = {}
        with open(self.cfg.session_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        for c in state.get('cookies', []):
            cookies[c['name']] = c['value']
        headers = {
            'User-Agent': UA,
            'Origin': CHZZK_ORIGIN,
            'Referer': f"{CHZZK_ORIGIN}/",
            'Accept': '*/*',
            'Connection': 'keep-alive',
        }
        timeout = aiohttp.ClientTimeout(total=None, connect=self.cfg.timeout_playlist)
        return aiohttp.ClientSession(headers=headers, cookies=cookies, timeout=timeout)

    async def _open_file(self):
        path = Path(self.cfg.out_path)
        if self.cfg.segment_seconds > 0:
            stem = path.with_suffix("")
            ts = _now_ts()
            path = Path(f"{stem}_{ts}.ts")
        self.cur_file_path = path
        self.current_file = await asyncio.to_thread(open, path, 'ab', buffering=0)

    async def _maybe_roll(self):
        if self.cfg.segment_seconds > 0 and (asyncio.get_event_loop().time() - self.started_time) >= self.cfg.segment_seconds:
            await asyncio.to_thread(self.current_file.close)
            await self._open_file()
            self.started_time = asyncio.get_event_loop().time()

    async def _pick_variant_if_master(self) -> str:
        assert self.session
        async with self.session.get(self.m3u8_url) as r:
            r.raise_for_status()
            text = await r.text()
        base = self.m3u8_url.rsplit('/', 1)[0] + '/'
        variants = _parse_master_variants(text, base)
        if variants:
            url = _choose_1080p(variants) if self.cfg.quality_prefer_1080 else variants[-1]
            return url or self.m3u8_url
        return self.m3u8_url

    async def _get_playlist_text(self, variant_url: str) -> Optional[str]:
        url = variant_url
        if self.cfg.llhls:
            params = {}
            if self.cur_msn:
                params["_HLS_msn"] = str(self.cur_msn)
            if self.cur_part:
                params["_HLS_part"] = str(self.cur_part)
            if params:
                url = _with_params(url, params)
        try:
            async with self.session.get(url) as r:
                if r.status in (401,403):
                    return None
                r.raise_for_status()
                return await r.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    async def _fetch_media(self, base: str, rel: str) -> bool:
        assert self.session and self.current_file
        media_url = urljoin(base, rel)
        try:
            to = aiohttp.ClientTimeout(total=None, sock_read=self.cfg.timeout_media, connect=self.cfg.timeout_media)
            async with self.session.get(media_url, timeout=to) as r:
                if r.status in (401,403):
                    return False
                r.raise_for_status()
                async for chunk in r.content.iter_chunked(64 * 1024):
                    if not chunk:
                        continue
                    await asyncio.to_thread(self.current_file.write, chunk)
            return True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def run(self):
        self.session = await self._create_session()
        variant_url = await self._pick_variant_if_master()
        await self._open_file()
        loop = asyncio.get_event_loop()
        self.started_time = loop.time()

        self.cur_msn, self.cur_part = 0, 0
        try:
            while not self.stop:
                # stall watchdog
                try:
                    sz = os.path.getsize(self.cur_file_path) if self.cur_file_path else 0
                except Exception:
                    sz = 0
                if sz > self.last_size:
                    self.last_size = sz
                    self.idle = 0
                else:
                    self.idle += 1
                    if self.idle >= self.cfg.stall_seconds:
                        self.cur_msn += 1
                        self.cur_part = 0
                        self.idle = 0

                # playlist
                txt = await self._get_playlist_text(variant_url)
                if not txt:
                    await asyncio.sleep(0.5)
                    continue
                msn, uris = _parse_media_playlist(txt)
                if msn is not None and self.cur_msn == 0:
                    self.cur_msn = msn + self.cfg.live_edge_bias
                    self.cur_part = 0
                base = variant_url.rsplit('/', 1)[0] + '/'

                # lightweight serial + small prefetch
                n = max(1, self.cfg.prefetch)
                for rel in uris[:n]:
                    ok = await self._fetch_media(base, rel)
                    if not ok:
                        self.cur_msn += 1
                        self.cur_part = 0
                        break
                    self.cur_part += 1

                await self._maybe_roll()
                await asyncio.sleep(0.1)
        finally:
            if self.current_file:
                await asyncio.to_thread(self.current_file.close)
            if self.session:
                await self.session.close()

    def stop_now(self):
        self.stop = True


# ================= Public API =================
async def _amain(live_details: dict, config: Optional[dict]):
    m3u8_url = live_details.get("m3u8_url")
    channel_name = _sanitize_name(live_details.get("channelName", "unknown_channel"))
    live_title = _sanitize_name(live_details.get("liveTitle", "unknown_title"))
    if not m3u8_url:
        print(f"[ERROR] m3u8_url not found for {channel_name}.")
        return None

    base_dir = Path("/app/recordings")
    streamer_dir = base_dir / channel_name
    streamer_dir.mkdir(parents=True, exist_ok=True)

    day_dir = _dt.datetime.now().strftime("%Y%m%d")
    log_dir = Path("/app/logs") / day_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    basename = f"{_now_ts()}_{live_title}"
    output_path = streamer_dir / f"{basename}.ts"

    cfg = _Cfg(
        session_path=(config or {}).get("session_path", "/app/config/session.json"),
        out_path=str(output_path),
        quality_prefer_1080=(config or {}).get("prefer_1080p", True),
        llhls=(config or {}).get("prefer_llhls", True),
        prefetch=int((config or {}).get("prefetch", 2)),
        stall_seconds=int((config or {}).get("stall_seconds", 15)),
        timeout_playlist=int((config or {}).get("timeout_playlist", 10)),
        timeout_media=int((config or {}).get("timeout_media", 6)),
        live_edge_bias=int((config or {}).get("live_edge_bias", 2)),
        segment_seconds=int((config or {}).get("segment_seconds", os.getenv("SEGMENT_SECONDS", 0) or 0)),
    )

    rec = _LLHLSRecorder(m3u8_url, cfg, log_dir)
    loop = asyncio.get_event_loop()
    task = loop.create_task(rec.run())

    proc = _RecorderProcess(stop_cb=rec.stop_now, desc=f"LLHLSRecorder:{channel_name}")

    return {
        "process": proc,
        "output": str(output_path),
        "channel": channel_name,
        "title": live_title,
        "timestamp": _now_ts(),
    }


def start_recording(live_details, config=None):
    try:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(_amain(live_details, config), loop)
            return fut.result()
        else:
            return asyncio.run(_amain(live_details, config))
    except Exception as e:
        print(f"[EXCEPTION] Unexpected error in start_recording: {e}")
        return None
