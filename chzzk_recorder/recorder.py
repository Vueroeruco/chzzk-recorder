#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import datetime as _dt
import subprocess
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urljoin

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
CHZZK_ORIGIN = "https://chzzk.naver.com"


def _sanitize_name(name: str) -> str:
    if not name:
        return "unknown"
    # allow letters, numbers, Korean Hangul ranges, spaces, underscore, hyphen
    pattern = r"[^\w\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F _-]"
    return re.sub(pattern, "", name).strip() or "unknown"


def _now_ts() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _headers(cookie_str: str, device_id: str) -> Dict[str, str]:
    return {
        'User-Agent': UA,
        'Origin': CHZZK_ORIGIN,
        'Referer': f'{CHZZK_ORIGIN}/',
        'Cookie': cookie_str,
        'Accept': 'application/vnd.apple.mpegurl,application/x-mpegURL,*/*',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'front-client-platform-type': 'PC',
        'front-client-product-type': 'web',
        'deviceid': device_id,
    }


def _select_best_variant(master_url: str, hdrs: Dict[str, str]) -> str:
    try:
        r = requests.get(master_url, headers=hdrs, timeout=8)
        if not r.ok:
            return master_url
        text = r.text
        if '#EXT-X-STREAM-INF' not in text:
            return master_url
        base = master_url.rsplit('/', 1)[0] + '/'
        lines = text.splitlines()
        best = None
        best_score = (-1, 0.0, -1)  # (height, fps, bandwidth)
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXT-X-STREAM-INF'):
                m_res = re.search(r'RESOLUTION=\s*(\d+)x(\d+)', line)
                h = int(m_res.group(2)) if m_res else -1
                m_bw = re.search(r'BANDWIDTH=\s*(\d+)', line)
                bw = int(m_bw.group(1)) if m_bw else -1
                m_fps = re.search(r'FRAME-RATE=\s*([0-9.]+)', line)
                fps = float(m_fps.group(1)) if m_fps else 0.0
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith('#'):
                    j += 1
                if j < len(lines):
                    uri = lines[j].strip()
                    cand = urljoin(base, uri)
                    score = (h, fps, bw)
                    if score > best_score:
                        best_score = score
                        best = cand
                i = j
            i += 1
        return best or master_url
    except Exception:
        return master_url


def start_recording(live_details: dict, config: Optional[dict] = None):
    try:
        m3u8_url = (live_details or {}).get('m3u8_url')
        channel_name = _sanitize_name((live_details or {}).get('channelName', 'unknown_channel'))
        live_title = _sanitize_name((live_details or {}).get('liveTitle', 'unknown_title'))
        if not m3u8_url:
            print(f"[ERROR] m3u8_url not found for {channel_name}.")
            return None

        base_dir = Path('/app/recordings')
        streamer_dir = base_dir / channel_name
        streamer_dir.mkdir(parents=True, exist_ok=True)

        day_dir = _dt.datetime.now().strftime('%Y%m%d')
        log_dir = Path('/app/logs') / day_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        basename = f"{_now_ts()}_{live_title}"

        # Previous files policy
        on_start_previous = (config or {}).get('on_start_previous', 'archive')
        archive_dir_cfg = (config or {}).get('archive_dir', '/app/recordings_archive')
        archive_dir = Path(archive_dir_cfg) / channel_name / _now_ts()
        try:
            if on_start_previous in ('archive', 'delete'):
                old_files = [p for p in streamer_dir.glob('*') if p.is_file() and not p.name.startswith('.')]
                if old_files:
                    if on_start_previous == 'archive':
                        archive_dir.mkdir(parents=True, exist_ok=True)
                        for p in old_files:
                            try:
                                p.replace(archive_dir / p.name)
                            except Exception:
                                pass
                        print(f"[ARCHIVE] Moved {len(old_files)} file(s) to {archive_dir}")
                    else:
                        for p in old_files:
                            try:
                                p.unlink(missing_ok=True)
                            except Exception:
                                pass
                        print(f"[CLEAN] Deleted {len(old_files)} previous file(s) in {streamer_dir}")
        except Exception as e:
            print(f"[WARN] Failed to prepare previous files: {e}")

        # Output path (TS)
        out_path = streamer_dir / f"{basename}.ts"

        # N_m3u8DL-RE 병렬 다운로더 (우선 사용)
        if bool((config or {}).get('use_n_m3u8dlre', False)):
            session_path = (config or {}).get('session_path', '/app/config/session.json')
            with open(session_path, 'r', encoding='utf-8') as f:
                st = json.load(f)
            cookies = {c['name']: c['value'] for c in st.get('cookies', [])}
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            device_id = cookies.get('ba.uuid', '4438f666-fa96-4d28-9cc8-39c460399cc8')
            hdrs = _headers(cookie_str, device_id)
            sel_url = _select_best_variant(m3u8_url, hdrs)

            headers_cli = []
            for k in ('User-Agent','Origin','Referer','Accept','Accept-Language'):
                v = hdrs.get(k)
                if v:
                    headers_cli += ['--header', f"{k}: {v}"]
            headers_cli += ['--header', f"Cookie: {cookie_str}"]

            threads = int((config or {}).get('n_m3u8dlre_threads', 8))
            perlog = open(str(log_dir / f"{_now_ts()}_{channel_name}_{live_title}_nmd.log"), 'a', encoding='utf-8')
            # N_m3u8DL-RE 옵션 정정: 실시간 머지(파이프 TS) 및 병렬 다운로드
            cmd = [
                'N_m3u8DL-RE', sel_url,
                '--live-real-time-merge',    # 실시간 파일 병합
                '--live-pipe-mux',           # ffmpeg 파이프로 TS 생성
                '-mt',                       # 오디오/비디오 동시 다운로드 플래그
                '--thread-count', str(threads),
                '--save-dir', str(streamer_dir),
                '--save-name', basename,
                '--no-ansi-color',           # 로그 제어문자 방지
            ] + headers_cli
            print(f"[NMD] Start -> {out_path} (headers redacted)")
            proc = subprocess.Popen(cmd, stdout=perlog, stderr=perlog)
            return {
                'process': proc,
                'output': str(out_path),
                'channel': channel_name,
                'title': live_title,
                'timestamp': _now_ts(),
                'log_dir': str(log_dir),
            }

        # N_m3u8DL-RE가 비활성화된 경우: 현재는 ffmpeg 대체 경로를 제거했으므로 종료
        print('[ERROR] N_m3u8DL-RE가 비활성화되어 녹화를 시작할 수 없습니다. config에서 "use_n_m3u8dlre": true 로 설정하세요.')
        return None

    except Exception as e:
        print(f"[EXCEPTION] Unexpected error in start_recording: {e}")
        return None
