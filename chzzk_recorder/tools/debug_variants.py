#!/usr/bin/env python3
import os, json, re, sys
from urllib.parse import urljoin
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'config')

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
ORIGIN = 'https://chzzk.naver.com'

def load_config():
    with open(os.path.join(CONFIG_DIR, 'config.json'), 'r', encoding='utf-8') as f:
        return json.load(f)

def load_cookies():
    with open(os.path.join(CONFIG_DIR, 'session.json'), 'r', encoding='utf-8') as f:
        st = json.load(f)
    return {c['name']: c['value'] for c in st.get('cookies', [])}

def headers_from_cookies(cookies: dict) -> dict:
    cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
    device_id = cookies.get('ba.uuid', '4438f666-fa96-4d28-9cc8-39c460399cc8')
    return {
        'User-Agent': UA,
        'Origin': ORIGIN,
        'Referer': f'{ORIGIN}/',
        'Cookie': cookie_str,
        'Accept': 'application/vnd.apple.mpegurl,application/x-mpegURL,*/*',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'front-client-platform-type': 'PC',
        'front-client-product-type': 'web',
        'deviceid': device_id,
    }

def get_live_details(channel_id: str, headers: dict) -> dict or None:
    url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_id}/live-detail"
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json().get('content')
    if not data:
        return None
    j = data.get('livePlaybackJson')
    if not j:
        return None
    obj = json.loads(j)
    m3u8 = None
    for m in obj.get('media', []) or []:
        if (m.get('mediaId','').lower() == 'hls'):
            m3u8 = m.get('path')
            break
    if not m3u8:
        return None
    return {
        'channelName': data.get('channel',{}).get('channelName'),
        'liveTitle': data.get('liveTitle'),
        'videoId': obj.get('meta',{}).get('videoId'),
        'm3u8_url': m3u8,
    }

def parse_variants(master_text: str, base: str):
    out = []
    lines = master_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXT-X-STREAM-INF'):
            m = re.search(r'RESOLUTION=\s*(\d+)x(\d+)', line)
            height = int(m.group(2)) if m else -1
            j = i+1
            while j < len(lines) and lines[j].strip().startswith('#'):
                j += 1
            if j < len(lines):
                uri = lines[j].strip()
                absu = urljoin(base, uri)
                out.append((absu, height, uri))
            i = j
        i += 1
    return out

def main():
    cfg = load_config()
    cookies = load_cookies()
    hdrs = headers_from_cookies(cookies)

    targets = cfg.get('TARGET_CHANNELS', [])
    print(f"Targets: {len(targets)}")
    for cid in targets:
        try:
            det = get_live_details(cid, hdrs)
        except Exception as e:
            print(f"- {cid}: live-detail error: {e}")
            continue
        if not det:
            print(f"- {cid}: offline or no m3u8")
            continue
        print(f"- {cid}: LIVE '{det['liveTitle']}' | videoId={det['videoId']}")
        m3u8 = det['m3u8_url']
        try:
            r = requests.get(m3u8, headers=hdrs, timeout=8)
            print(f"  master status={r.status_code} bytes={len(r.content)}")
            if r.ok:
                base = m3u8.rsplit('/',1)[0] + '/'
                vars = parse_variants(r.text, base)
                if vars:
                    print("  variants:")
                    for u,h,raw in sorted(vars, key=lambda x: x[1]):
                        print(f"    - h={h:>4} uri={raw}")
                    # probe 1080 or highest
                    best = max(vars, key=lambda x: x[1])
                    probe = next((v for v in vars if v[1] >= 1080), best)
                    pr = requests.get(probe[0], headers=hdrs, timeout=8)
                    print(f"  probe playlist h={probe[1]} status={pr.status_code} bytes={len(pr.content)}")
                else:
                    print("  no #EXT-X-STREAM-INF found (likely media playlist)")
            else:
                print("  master fetch failed")
        except Exception as e:
            print(f"  master request error: {e}")

if __name__ == '__main__':
    main()

