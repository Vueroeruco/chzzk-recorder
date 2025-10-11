import time
import json
import os
import datetime
from chzzk_api import ChzzkAPI
from recorder import start_recording
from auth import get_session_cookies

# State dictionary to manage recording processes
currently_recording = {}


def load_config(config_path):
    """Loads the configuration from config.json."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main_loop():
    """The main loop to watch for live channels and trigger recordings."""

    # --- Initial Setup ---
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(base_dir, 'config')
    config_path = os.path.join(config_dir, 'config.json')
    session_path = os.path.join(config_dir, 'session.json')

    if not os.path.exists(config_path):
        print(f"Error: Config file not found at {config_path}. Please run auth.py first.")
        return
    config = load_config(config_path)

    target_ids = set(config.get("TARGET_CHANNELS", []))
    if not target_ids:
        print("No target channels specified in config.json. Watcher will exit.")
        return

    polling_interval = config.get("POLLING_INTERVAL_SECONDS", 30)
    stall_restart_seconds = int(config.get("stall_restart_seconds", 180))
    last_refresh_hour = -1

    try:
        api = ChzzkAPI(config_dir)
    except FileNotFoundError as e:
        print(f"Session file not found: {e}. Please run auth.py to create it.")
        return

    print(f"Watcher started. Monitoring {len(target_ids)} channel(s)...")

    # --- Main Loop ---
    while True:
        now = datetime.datetime.now()
        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] Checking status...")

        # 1. Session Refresh Logic
        if now.hour in [6, 18] and now.hour != last_refresh_hour:
            print(f"--- Scheduled session refresh triggered at {now.hour}:00 ---")
            refresh_success = get_session_cookies(config_path, session_path, headless=True)
            last_refresh_hour = now.hour

            if refresh_success:
                print("Session refreshed successfully. Re-initializing API module.")
                api = ChzzkAPI(config_dir)
                # Do NOT restart active recordings to avoid file splits.
                if currently_recording:
                    print("Active recordings detected — skipping restart to preserve single files.")
                else:
                    print("No active recordings at refresh time.")
            else:
                print("Session refresh failed. Will retry at the next scheduled time.")

        # 2. Process Health/Progress Check
        for channel_id, info in list(currently_recording.items()):
            # If process exited, cleanup
            if info['process'].poll() is not None:
                print(f"! Recording process for '{info['channel_name']}' ({channel_id}) found dead. Cleaning up.")
                del currently_recording[channel_id]
                continue
            # Stall detection on output file size
            out_path = info.get('output')
            if not out_path:
                continue
            try:
                sz = os.path.getsize(out_path)
            except Exception:
                sz = -1
            last_sz = info.get('last_size', -2)
            last_grow = info.get('last_grow', time.time())
            now_ts = time.time()
            if sz is not None and sz >= 0:
                if sz > last_sz:
                    info['last_size'] = sz
                    info['last_grow'] = now_ts
                else:
                    # no growth
                    if (now_ts - last_grow) >= stall_restart_seconds:
                        print(f"! Stall detected for '{info['channel_name']}' ({channel_id}). size={sz}, last_grow={int(now_ts - last_grow)}s >= {stall_restart_seconds}s. Restarting.")
                        try:
                            info['process'].kill()
                        except Exception:
                            pass
                        del currently_recording[channel_id]
                        # try immediate restart with fresh details
                        try:
                            det = api.get_live_details(channel_id)
                            if det and det.get('m3u8_url'):
                                restarted = start_recording(det, config)
                                if restarted and restarted.get('process'):
                                    currently_recording[channel_id] = {
                                        'process': restarted['process'],
                                        'channel_name': det.get('channelName', channel_id),
                                        'output': restarted.get('output'),
                                        'title': restarted.get('title'),
                                        'log_dir': restarted.get('log_dir'),
                                        'last_size': 0,
                                        'last_grow': time.time(),
                                    }
                                    print(f"  -> Restarted recording for '{currently_recording[channel_id]['channel_name']}' ({channel_id})")
                        except Exception as e:
                            print(f"  -> Restart attempt failed: {e}")

        # 3. Check Live Status
        try:
            live_channels_details = {cid: api.get_live_details(cid) for cid in target_ids}
            live_channels_details = {k: v for k, v in live_channels_details.items() if v}  # Filter out non-live
        except Exception as e:
            print(f"Error during API call: {e}. Skipping this check cycle.")
            time.sleep(polling_interval)
            continue

        live_now_ids = set(live_channels_details.keys())

        # 4. Start New Recordings
        for channel_id in live_now_ids:
            if channel_id not in currently_recording:
                details = live_channels_details[channel_id]
                channel_name = details.get("channelName", channel_id)
                print(f"  -> New live stream detected for '{channel_name}' ({channel_id})")

                started_info = start_recording(details, config)
                if started_info and started_info.get("process"):
                    process = started_info["process"]
                    print(f"     Recording process started for '{channel_name}' (PID: {process.pid})")
                    currently_recording[channel_id] = {
                        "process": process,
                        "channel_name": channel_name,
                        "output": started_info.get("output"),
                        "title": started_info.get("title"),
                        "log_dir": started_info.get("log_dir"),
                        "last_size": 0,
                        "last_grow": time.time(),
                    }
                else:
                    print(f"     Failed to start recording for {channel_id}.")

        # 5. Stop Old Recordings
        for channel_id in list(currently_recording.keys()):
            if channel_id not in live_now_ids:
                recording_info = currently_recording[channel_id]
                print(f"  -> Stream ended for '{recording_info['channel_name']}' ({channel_id})")
                try:
                    recording_info['process'].kill()
                    print(f"     Recording process for '{recording_info['channel_name']}' terminated.")
                except Exception as e:
                    print(f"     An unexpected error occurred during process termination: {e}")
                del currently_recording[channel_id]

        # --- Reporting ---
        if not currently_recording:
            print("No target channels are currently live or being recorded.")
        else:
            recording_names = [info['channel_name'] for info in currently_recording.values()]
            print(f"Currently recording: {recording_names}")

        print(f"Check complete. Waiting for {polling_interval} seconds.")
        time.sleep(polling_interval)


if __name__ == "__main__":
    # Change directory to the script's location
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main_loop()
