import os
import json
import getpass
from chzzk_api import ChzzkAPI
from auth import get_session_cookies, load_config

def select_channels(api):
    """Fetches followed channels and lets the user select which ones to record."""
    print("\nFetching your followed channels...")
    followed_list = api.get_followed_channels()

    if not followed_list:
        print("Could not find any followed channels. Please follow some channels on Chzzk first.")
        return []

    print("--- Your Followed Channels ---")
    for i, item in enumerate(followed_list):
        channel_name = item.get('channel', {}).get('channelName', 'Unknown Channel')
        print(f"  [{i + 1}] {channel_name}")
    print("-----------------------------")

    while True:
        try:
            choice = input("\nEnter the numbers of the channels you want to record, separated by commas (e.g., 1, 3, 5): ")
            selected_indices = [int(i.strip()) - 1 for i in choice.split(',')]
            
            target_channels = []
            invalid_numbers = []
            for i in selected_indices:
                if 0 <= i < len(followed_list):
                    channel_id = followed_list[i].get('channel', {}).get('channelId')
                    if channel_id:
                        target_channels.append(channel_id)
                else:
                    invalid_numbers.append(i + 1)
            
            if invalid_numbers:
                print(f"\nError: The following numbers are invalid: {invalid_numbers}. Please try again.")
                continue

            if not target_channels:
                print("\nError: You didn't select any valid channels. Please try again.")
                continue

            selected_names = [followed_list[i].get('channel', {}).get('channelName') for i in selected_indices]
            print(f"\nYou have selected: {selected_names}")
            return target_channels

        except ValueError:
            print("\nError: Invalid input. Please enter numbers separated by commas.")
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")

    return []

def main():
    """Main setup function to guide the user through configuration."""
    print("--- Chzzk Recorder Setup ---")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(base_dir, 'config')
    config_path = os.path.join(config_dir, 'config.json')
    session_path = os.path.join(config_dir, 'session.json')

    os.makedirs(config_dir, exist_ok=True)

    # 1. Get and Validate Credentials
    while True:
        print("\nPlease enter your Naver credentials.")
        chzzk_id = input("  - Naver ID: ")
        chzzk_pw = getpass.getpass("  - Naver Password: ")

        temp_config = {"CHZZK_ID": chzzk_id, "CHZZK_PW": chzzk_pw}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(temp_config, f)

        print("\nAttempting to log in to verify your credentials...")
        login_success = get_session_cookies(config_path, session_path, headless=True)

        if login_success:
            print("\nLogin successful!")
            break
        else:
            print("\nLogin failed. Please check your credentials and try again.")
            # Clean up failed config
            if os.path.exists(config_path):
                os.remove(config_path)
            retry = input("Do you want to try again? (y/n): ").lower()
            if retry != 'y':
                return

    # 2. Select Target Channels
    try:
        api = ChzzkAPI(config_dir)
        target_channels = select_channels(api)
        if not target_channels:
            print("No channels selected. Exiting setup.")
            return
    except Exception as e:
        print(f"Failed to initialize API and select channels: {e}")
        return

    # 3. Set Download Path
    default_path = os.path.join(base_dir, 'recordings')
    print(f"\nThe default download path is: {default_path}")
    use_default = input("Do you want to use this path? (y/n): ").lower()
    
    download_path = default_path
    if use_default != 'y':
        while True:
            new_path = input("Enter the new download path: ")
            try:
                # Test if path is valid and writable
                os.makedirs(new_path, exist_ok=True)
                test_file = os.path.join(new_path, 'test.tmp')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                download_path = new_path
                print(f"Download path set to: {download_path}")
                break
            except Exception as e:
                print(f"Error: The path '{new_path}' is not valid or not writable. {e}")
                retry = input("Do you want to try a different path? (y/n): ").lower()
                if retry != 'y':
                    download_path = default_path
                    print(f"Using default download path: {download_path}")
                    break

    # 4. Finalize and Save Config
    final_config = {
        "CHZZK_ID": chzzk_id,
        "CHZZK_PW": chzzk_pw,
        "TARGET_CHANNELS": target_channels,
        "DOWNLOAD_PATH": download_path,
        "POLLING_INTERVAL_SECONDS": 30
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(final_config, f, indent=4)

    print("\n-------------------------------------")
    print("Setup complete! config.json has been created.")
    print("You can now run watcher.py to start monitoring and recording.")
    print("-------------------------------------")

if __name__ == "__main__":
    main()
