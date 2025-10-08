import os
import re
import subprocess
import datetime
import json
import requests

def sanitize_name(name: str) -> str:
    """
    Removes unsafe characters for filenames while keeping Korean, English, numbers, spaces, and underscores.
    """
    if not name:
        return "unknown"
    return re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ _]", "", name).strip() or "unknown"


def get_auth_headers(session_path):
    """
    Loads cookies from session.json and prepares a header string for ffmpeg.
    """
    if not os.path.exists(session_path):
        raise FileNotFoundError(f"Session file not found at {session_path}")

    with open(session_path, "r", encoding="utf-8") as f:
        storage_state = json.load(f)

    cookies = {cookie["name"]: cookie["value"] for cookie in storage_state["cookies"]}
    cookie_string = "; ".join([f"{name}={value}" for name, value in cookies.items()])

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://chzzk.naver.com/",
        "Origin": "https://chzzk.naver.com",
        "Cookie": cookie_string,
    }

    # Format for ffmpeg's -headers option
    header_string = ""
    for key, value in headers.items():
        header_string += f"{key}: {value}\n"
    return header_string


def get_1080p_stream_url(m3u8_url: str, headers: dict) -> str:
    """
    Fetches the master m3u8 playlist and returns the URL for the 1080p stream.
    Returns the original m3u8_url if no 1080p stream is found.
    """
    try:
        response = requests.get(m3u8_url, headers=headers)
        response.raise_for_status()
        
        playlist_content = response.text
        lines = playlist_content.strip().split('\n')
        
        stream_url = None
        for i, line in enumerate(lines):
            if "1080p" in line and i + 1 < len(lines):
                stream_url = lines[i+1]
                break
        
        if stream_url:
            # If the URL is relative, construct the absolute URL
            if not stream_url.startswith("http"):
                base_url = m3u8_url.rsplit('/', 1)[0]
                stream_url = f"{base_url}/{stream_url}"
            print(f"[INFO] Found 1080p stream: {stream_url}")
            return stream_url

    except requests.RequestException as e:
        print(f"[WARNING] Could not fetch or parse master playlist: {e}")
    
    print("[INFO] 1080p stream not found, using master m3u8 URL.")
    return m3u8_url


def start_recording(live_details, config):
    """
    Starts recording a live stream using ffmpeg directly with auto reconnect options.
    Saves into streamer-specific folders with safe Korean filenames.
    """
    try:
        m3u8_url = live_details.get("m3u8_url")
        channel_name = live_details.get("channelName", "unknown_channel")
        live_title = live_details.get("liveTitle", "unknown_title")

        if not m3u8_url:
            print(f"[ERROR] m3u8_url not found for {channel_name}.")
            return None

        # Sanitize names
        safe_channel_name = sanitize_name(channel_name)
        safe_live_title = sanitize_name(live_title)

        print(f"[INFO] Preparing to record: '{safe_live_title}' by '{safe_channel_name}'")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # === Directory setup ===
        base_dir = "/app/recordings"
        streamer_dir = os.path.join(base_dir, safe_channel_name)
        os.makedirs(streamer_dir, exist_ok=True)

        day_dir = datetime.datetime.now().strftime("%Y%m%d")
        log_dir = os.path.join("/app/logs", day_dir)
        os.makedirs(log_dir, exist_ok=True)

        # === Output path ===
        basename = f"{timestamp}_{safe_live_title}"
        output_path = os.path.join(streamer_dir, f"{basename}.ts")

        print(f"[INFO] Output path: {output_path}")

        # === Headers from cookies ===
        session_path = "/app/config/session.json"
        ffmpeg_headers = get_auth_headers(session_path)
        
        # Convert ffmpeg header string to a dict for requests
        request_headers = {line.split(": ")[0]: line.split(": ")[1] for line in ffmpeg_headers.strip().split('\n') if ": " in line}

        # === Select 1080p stream ===
        recording_url = get_1080p_stream_url(m3u8_url, request_headers)

        # === ffmpeg command ===
        command = [
            "ffmpeg",
            "-y",  # Overwrite
            "-headers", ffmpeg_headers.replace("\r\n", "\n"),
            "-user_agent", "Mozilla/5.0",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_on_network_error", "1",
            "-reconnect_delay_max", "10",
            "-rw_timeout", "15000000",
            "-timeout", "15000000",
            "-allowed_extensions", "ALL",
            "-i", recording_url,
            "-c", "copy",
            "-fflags", "+genpts",
            output_path,
        ]

        # === Log paths ===
        stdout_path = os.path.join(log_dir, f"{basename}_stdout.log")
        stderr_path = os.path.join(log_dir, f"{basename}_stderr.log")

        # === Start ffmpeg ===
        stdout_log = open(stdout_path, "w", encoding="utf-8")
        stderr_log = open(stderr_path, "w", encoding="utf-8")

        print(f"[INFO] Starting ffmpeg...")
        process = subprocess.Popen(command, stdout=stdout_log, stderr=stderr_log)

        return {
            "process": process,
            "output": output_path,
            "channel": safe_channel_name,
            "title": safe_live_title,
            "timestamp": timestamp,
        }

    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return None
    except Exception as e:
        print(f"[EXCEPTION] Unexpected error in start_recording: {e}")
        return None
