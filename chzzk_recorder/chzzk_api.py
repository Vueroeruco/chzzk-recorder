
import json
import os
import requests
import time

class ChzzkAPI:
    def __init__(self, config_dir):
        self.session_path = os.path.join(config_dir, "session.json")
        self.headers = self._prepare_headers()

    def _prepare_headers(self):
        """Loads cookies from session file and prepares headers for API requests."""
        if not os.path.exists(self.session_path):
            raise FileNotFoundError(f"Session file not found at {self.session_path}. Please run install.py first.")

        with open(self.session_path, "r") as f:
            storage_state = json.load(f)
        
        cookies = {cookie['name']: cookie['value'] for cookie in storage_state['cookies']}
        cookie_string = "; ".join([f"{name}={value}" for name, value in cookies.items()])

        # Find the specific deviceId from cookies if it exists, otherwise use a default.
        # Based on cURL.txt, a static deviceId seems to work.
        device_id = cookies.get("ba.uuid", "4438f666-fa96-4d28-9cc8-39c460399cc8")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Origin': 'https://chzzk.naver.com',
            'Referer': 'https://chzzk.naver.com/',
            'Cookie': cookie_string,
            'deviceid': device_id,
            'front-client-platform-type': 'PC',
            'front-client-product-type': 'web'
        }
        return headers

    def get_followed_channels(self):
        """
        Fetches the list of followed channels that are currently live.
        Based on the cURL command provided.
        """
        url = "https://api.chzzk.naver.com/service/v1/channels/followings?page=0&size=500&sortType=FOLLOW"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            
            data = response.json()
            followed_channels = data.get('content', {}).get('followingList', [])
            return followed_channels

        except requests.exceptions.RequestException as e:
            print(f"An error occurred while fetching live followings: {e}")
            return None
        except json.JSONDecodeError:
            print(f"Failed to decode JSON from response. Response text: {response.text}")
            return None

    def get_channel_info(self, channel_id):
        """Fetches channel information for a given channel_id."""
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json().get('content', {})
        except requests.exceptions.RequestException as e:
            print(f"An error occurred while fetching channel info for {channel_id}: {e}")
            return None
        except json.JSONDecodeError:
            print(f"Failed to decode JSON from response for {channel_id}. Response text: {response.text}")
            return None

    def get_live_details(self, channel_id, retries=3, delay=2):
        """
        Fetches live stream details for a given channel_id.
        Includes retry logic for temporary API inconsistencies.
        """
        url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_id}/live-detail"
        
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                content = data.get('content')

                if not content:
                    print(f"DEBUG: Channel {channel_id} appears offline. API response content was empty: {data}")
                    # This is a definitive offline status, no need to retry.
                    return None

                # Adult channel check
                if content.get("adult") and not self.headers.get("Cookie", "").__contains__("NID_SES"):
                     print(f"WARNING: Channel {channel_id} is for adults and requires full authentication (NID_SES cookie). Skipping.")
                     return None

                live_playback_json_str = content.get("livePlaybackJson")
                if not live_playback_json_str:
                    # This could be a temporary state, especially if status is not 'ENDED'
                    if content.get('status') == 'ENDED':
                        print(f"DEBUG: Channel {channel_id} status is 'ENDED'. No retry needed.")
                        return None # Stream has definitively ended.
                    
                    print(f"DEBUG: 'livePlaybackJson' is missing for channel {channel_id}, retrying... ({attempt + 1}/{retries})")
                    time.sleep(delay)
                    continue # Go to next attempt

                live_playback_data = json.loads(live_playback_json_str)
                m3u8_url = None
                if live_playback_data.get("media") and isinstance(live_playback_data["media"], list):
                    for media_item in live_playback_data["media"]:
                        if media_item.get("mediaId", "").lower() == "hls":
                            m3u8_url = media_item.get("path")
                            break

                if m3u8_url:
                    # Success, return details
                    return {
                        "liveTitle": content.get("liveTitle"),
                        "channelName": content.get("channel", {}).get("channelName"),
                        "videoId": live_playback_data.get("meta", {}).get("videoId"),
                        "m3u8_url": m3u8_url
                    }
                else:
                    # m3u8_url not found, could be temporary
                    print(f"DEBUG: HLS m3u8 URL not found for channel {channel_id}, retrying... ({attempt + 1}/{retries})")
                    time.sleep(delay)
                    continue # Go to next attempt

            except requests.exceptions.RequestException as e:
                print(f"An error occurred while fetching live details for {channel_id}: {e}, retrying... ({attempt + 1}/{retries})")
                time.sleep(delay)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Failed to parse JSON from response for {channel_id}. Error: {e}. Response text: {response.text}")
                # This is a critical error, no retry
                return None
        
        # If all retries fail
        print(f"All retries failed for channel {channel_id}. Assuming offline.")
        return None

if __name__ == '__main__':
    # Example usage:
    # Assumes the script is run from a directory where 'config' is a subdirectory.
    # To run from project root: python -m chzzk_recorder.chzzk_api
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_directory = os.path.join(current_dir, 'config')

    print(f"Looking for session file in: {config_directory}")

    try:
        api = ChzzkAPI(config_directory)
        followed_channels = api.get_followed_channels()

        if followed_channels:
            print(f"\nFound {len(followed_channels)} followed channel(s). Checking for live status...")
            found_live_channel = False
            for item in followed_channels:
                channel = item.get('channel', {})
                channel_id = channel.get('channelId')
                channel_name = channel.get('channelName')
                
                if not channel_id or not channel_name:
                    continue

                print(f"\nChecking: {channel_name} ({channel_id})")
                live_details = api.get_live_details(channel_id)
                
                if live_details and live_details.get('m3u8_url'):
                    found_live_channel = True
                    print(f"  [LIVE] '{live_details['liveTitle']}'")
                    print(f"  -> Video ID: {live_details['videoId']}")
                    print(f"  -> m3u8 URL: {live_details['m3u8_url']}")
                else:
                    print("  [OFFLINE]")
            
            if not found_live_channel:
                print("\nNo followed channels are currently live.")

        elif followed_channels is None:
            print("\nCould not fetch followed channels. Check for errors above.")
        else:
            print("\nNo channels are being followed.")

    except FileNotFoundError as e:
        print(e)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
