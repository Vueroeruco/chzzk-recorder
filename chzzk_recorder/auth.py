import os
import json
from playwright.sync_api import sync_playwright, TimeoutError

def get_session_cookies(config_path, session_path, headless=True):
    """
    Launches a browser, automatically logs in, and saves the session state.
    Can be run in headless mode for automated renewal.
    """
    try:
        config = load_config(config_path)
        if not config.get("CHZZK_ID") or not config.get("CHZZK_PW"):
            raise ValueError("CHZZK_ID and CHZZK_PW must be set in config.")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading configuration: {e}")
        return False

    print("Attempting to refresh session cookies...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless, args=['--no-sandbox'])
            context = browser.new_context()
            page = context.new_page()

            page.goto("https://nid.naver.com/nidlogin.login", timeout=60000)

            page.locator("#id").fill(config["CHZZK_ID"])
            page.locator("#pw").fill(config["CHZZK_PW"])
            page.locator("button[type=submit]").click()

            # If not headless, user might need to do 2FA/captcha
            if not headless:
                print("Login submitted. Please complete any 2FA or CAPTCHA in the browser window.")
                wait_time = 300000 # 5 minutes for manual login
            else:
                # In headless mode, we expect login to be faster
                wait_time = 60000 # 1 minute

            page.wait_for_url("https://www.naver.com/**", timeout=wait_time)
            print("Login to Naver successful. Fetching Chzzk session...")
            
            page.goto("https://chzzk.naver.com/", wait_until="load", timeout=60000)
            
            storage = context.storage_state()
            with open(session_path, "w") as f:
                json.dump(storage, f)

            print(f"Session information successfully saved to '{session_path}'")
            return True

        except TimeoutError:
            print("Error: Session refresh process timed out.")
            if headless:
                print("This might be due to a new CAPTCHA or 2FA requirement. Try running in non-headless mode.")
            return False
        except Exception as e:
            print(f"An unexpected error occurred during session refresh: {e}")
            return False
        finally:
            if 'browser' in locals() and browser.is_connected():
                browser.close()

def load_config(config_path):
    """
    Loads the configuration from config.json.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    # Ensure the script runs in its own directory context
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    config_dir = os.path.join(os.getcwd(), 'config')
    config_path = os.path.join(config_dir, 'config.json')
    session_path = os.path.join(config_dir, 'session.json')

    # Create config directory if it doesn't exist
    os.makedirs(config_dir, exist_ok=True)

    # If config file doesn't exist, create it by asking for user input
    if not os.path.exists(config_path):
        print("Configuration file not found. Let's create one.")
        try:
            chzzk_id = input("Enter your Naver ID: ")
            chzzk_pw = input("Enter your Naver Password: ")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"CHZZK_ID": chzzk_id, "CHZZK_PW": chzzk_pw, "TARGET_CHANNELS": []}, f, indent=4)
            print(f"Created a new config file at {config_path}")
        except Exception as e:
            print(f"Could not create new config file: {e}")
            exit(1)

    print("--- Initial Setup or Manual Refresh ---")
    # When run directly, execute with headless=False for manual login.
    get_session_cookies(config_path, session_path, headless=False)