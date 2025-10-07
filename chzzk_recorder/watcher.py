import os
import sys
import json
import time
import datetime
import requests
import subprocess
from recorder import start_recording

# === CONFIG ===
CONFIG_PATH = "/app/config/config.json"
CHECK_INTERVAL = 30  # seconds between status checks
RETRY_DELAY = 10     # seconds before retry if API fails

# === Helper: Log formatting ===
def log(msg, level="INFO"):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{level}] {msg}", flush=True)


# === Helper: Load config ===
def load_config():
    if not os.path.exists(CONFIG_PATH):
        log(f"Config file not found at {CONFIG_PATH}", "ERROR")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# === Helper: Get live info from Chzzk API ===
def fetch_live_details(channel):
    """Fetches live status and m3u8 URL."""
    try:
        api_url = f"https://api.chzzk.naver.com/service/v1/channels/{channel}/live-detail"
        res = requests.get(api_url, timeout=10)
        if res.status_code != 200:
            log(f"API returned status {res.status_code} for {channel}", "WARN")
            return None

        data = res.json().get("content")
        if not data or not data.get("status") == "OPEN":
            return None

        # liveTitle, channelName, m3u8_url
        live_details = {
            "liveTitle": data.get("liveTitle"),
            "channelName": data["channel"]["channelName"],
            "m3u8_url": data.get("media", {}).get("mediaId"),
        }

        if live_details["m3u8_url"]:
            # Convert mediaId to m3u8 url if necessary
            media = data.get("media")
            if media and media.get("uri"):
                live_details["m3u8_url"] = media["uri"]

        return live_details

    except Exception as e:
        log(f"Error fetching live details for {channel}: {e}", "ERROR")
        return None


# === Main watcher loop ===
def main():
    config = load_config()
    channels = config.get("TARGET_CHANNELS", [])
    if not channels:
        log("No channels found in config.json (key: selected_channels)", "ERROR")
        return

    processes = {}  # channel_id -> {"process": Popen, "info": live_details}

    log(f"Watcher started. Monitoring {len(channels)} channel(s)...")

    try:
        while True:
            for channel in channels:
                try:
                    live_details = fetch_live_details(channel)
                    if not live_details:
                        # 방송이 꺼져 있음
                        if channel in processes and processes[channel]["process"].poll() is not None:
                            log(f"{processes[channel]['info']['channelName']} 방송 종료 감지, 프로세스 정리 중...")
                            processes.pop(channel, None)
                        continue

                    # 이미 녹화 중인지 확인
                    if channel in processes:
                        proc = processes[channel]["process"]
                        if proc.poll() is None:
                            # still running
                            continue
                        else:
                            log(f"{live_details['channelName']} 녹화 프로세스 종료됨, 재시작 중...")
                            time.sleep(RETRY_DELAY)
                            rec = start_recording(live_details, config)
                            if rec:
                                processes[channel] = rec
                            continue

                    # 새로 방송 시작됨
                    log(f"{live_details['channelName']} 방송 감지됨 — 녹화 시작 중...")
                    rec = start_recording(live_details, config)
                    if rec:
                        processes[channel] = rec
                        log(f"{live_details['channelName']} 녹화 시작 완료.")
                    else:
                        log(f"{live_details['channelName']} 녹화 실패.", "ERROR")

                except Exception as e:
                    log(f"Error processing channel {channel}: {e}", "ERROR")
                    time.sleep(RETRY_DELAY)

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log("KeyboardInterrupt detected — stopping all recorders...", "WARN")
        for ch, rec in processes.items():
            proc = rec["process"]
            if proc.poll() is None:
                proc.terminate()
        log("All ffmpeg processes terminated. Exiting watcher.")
    except Exception as e:
        log(f"Fatal error in watcher: {e}", "ERROR")


if __name__ == "__main__":
    main()
