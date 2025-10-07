import os
import subprocess
import datetime
import json

def get_auth_headers(session_path):
    """
    Loads cookies from session.json and prepares a header string for ffmpeg.
    """
    if not os.path.exists(session_path):
        raise FileNotFoundError(f"Session file not found at {session_path}")

    with open(session_path, "r") as f:
        storage_state = json.load(f)
    
    cookies = {cookie['name']: cookie['value'] for cookie in storage_state['cookies']}
    cookie_string = "; ".join([f"{name}={value}" for name, value in cookies.items()])

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://chzzk.naver.com/',
        'Origin': 'https://chzzk.naver.com',
        'Cookie': cookie_string
    }
    
    # Format for ffmpeg's -headers option
    header_string = ""
    for key, value in headers.items():
        header_string += f"{key}: {value}\r\n"
        
    return header_string

def start_recording(live_details, config):
    """
    Starts recording a live stream using ffmpeg directly.
    """
    try:
        m3u8_url = live_details.get("m3u8_url")
        channel_name = live_details.get("channelName", "unknown_channel")
        live_title = live_details.get("liveTitle", "unknown_title")

        if not m3u8_url:
            print(f"Error: m3u8_url not found for {channel_name}.")
            return None

        # Clean channel and title for file names
        safe_channel_name = "".join(c for c in channel_name if c.isalnum() or c in (' ', '_')).rstrip()
        safe_live_title = "".join(c for c in live_title if c.isalnum() or c in (' ', '_')).rstrip()

        print(f"Preparing to record stream using ffmpeg: '{safe_live_title}' by '{safe_channel_name}'")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        basename = f"{timestamp}_{safe_channel_name}_{safe_live_title}"
        
        # The output path is fixed inside the container.
        # The actual host path is determined by the volume mount in docker-compose.yml.
        download_dir = "/app/recordings"
        os.makedirs(download_dir, exist_ok=True)
        output_path = os.path.join(download_dir, f"{basename}.ts")

        print(f"  -> Starting recording...")
        print(f"  -> Output path: {output_path}")

        session_path = os.path.join(base_dir, "config", "session.json")
        headers = get_auth_headers(session_path)

        command = [
            'ffmpeg',
            '-y',  # Overwrite output file if it exists
            '-headers', headers,
            '-allowed_extensions', 'ALL',
            '-i', m3u8_url,
            '-c', 'copy', # Copy stream without re-encoding
            output_path
        ]

        log_dir = os.path.join(base_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        stdout_log = open(os.path.join(log_dir, f"{basename}_stdout.log"), 'w', encoding='utf-8')
        stderr_log = open(os.path.join(log_dir, f"{basename}_stderr.log"), 'w', encoding='utf-8')

        process = subprocess.Popen(command, stdout=stdout_log, stderr=stderr_log)
        
        # Return process without cookie_file as it's no longer used
        return {"process": process}

    except FileNotFoundError as e:
        print(f"Error: {e}. Make sure session.json exists.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred in start_recording: {e}")
        return None