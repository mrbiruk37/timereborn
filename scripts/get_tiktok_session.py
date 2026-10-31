"""Script to automatically log in to TikTok and capture session credentials."""

import os
import time
from pathlib import Path
from dotenv import load_dotenv, set_key

load_dotenv()
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def capture_tiktok_session():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: pip install playwright")
        return

    print("=" * 60)
    print("Opening TikTok Login in a browser window...")
    print("Sign in using your TikTok account (QR code, Google, Email, etc.)")
    print("=" * 60)

    with sync_playwright() as p:
        # Launch using installed Google Chrome or Edge (no extra download needed)
        try:
            browser = p.chromium.launch(headless=False, channel="chrome")
        except Exception:
            try:
                browser = p.chromium.launch(headless=False, channel="msedge")
            except Exception:
                browser = p.chromium.launch(headless=False)

        context = browser.new_context()
        page = context.new_page()

        page.goto("https://www.tiktok.com/login")

        session_id = None
        # Poll for sessionid cookie for up to 3 minutes
        start_time = time.time()
        while time.time() - start_time < 180:
            cookies = context.cookies()
            for c in cookies:
                if c.get("name") == "sessionid" and c.get("value"):
                    session_id = c.get("value")
                    break

            if session_id:
                break
            time.sleep(2)

        browser.close()

        if session_id:
            print("\n" + "=" * 60)
            print("SUCCESS! Your TikTok Session ID was captured!")
            print("=" * 60)
            print(f"TIKTOK_SESSION_ID={session_id}")

            if ENV_FILE.exists():
                set_key(str(ENV_FILE), "TIKTOK_SESSION_ID", session_id)
                print(f"Successfully saved to your local .env file!")
            print("=" * 60)
            print("Next step: Add TIKTOK_SESSION_ID to your GitHub Repository Secrets")
            print("=" * 60)
        else:
            print("\nTimed out waiting for login. Please try again.")


if __name__ == "__main__":
    capture_tiktok_session()

