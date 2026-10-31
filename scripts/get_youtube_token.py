#!/usr/bin/env python3
"""One-time local authentication script to acquire YouTube OAuth Refresh Token.

Scopes requested:
- youtube.upload: Resumable video uploading
- youtube.readonly: View channel data and video list
- youtube.force-ssl: Read and reply to comments
- yt-analytics.readonly: Fetch video performance analytics

Prerequisites:
1. Create a Google Cloud Project with YouTube Data API v3 and YouTube Analytics API enabled.
2. Create OAuth 2.0 Credentials (type: Desktop App or Web App).
3. Set YT_CLIENT_ID and YT_CLIENT_SECRET in your .env file OR provide client_secrets.json.
"""

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main():
    print("=" * 60)
    print(" Timereborn - YouTube OAuth 2.0 Token Generator ")
    print("=" * 60)

    client_id = os.getenv("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET")
    client_secrets_file = Path("client_secrets.json")

    flow = None

    if client_secrets_file.exists():
        print(f"Found {client_secrets_file}, using file config...")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
    elif client_id and client_secret:
        print("Using YT_CLIENT_ID and YT_CLIENT_SECRET from environment/.env...")
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/", "urn:ietf:wg:oauth:2.0:oob"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    else:
        print("\nNo client credentials detected!")
        print("Please provide your Google Cloud OAuth Client ID and Secret:")
        client_id = input("Enter YT_CLIENT_ID: ").strip()
        client_secret = input("Enter YT_CLIENT_SECRET: ").strip()

        if not client_id or not client_secret:
            print("Error: Both Client ID and Client Secret are required.")
            sys.exit(1)

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/", "urn:ietf:wg:oauth:2.0:oob"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("\nStarting local authentication server on http://localhost:8080...")
    print("A browser window will open. Sign in to the YouTube channel you want Timereborn to manage.\n")

    try:
        # prompt="consent" forces Google to return a refresh_token on every run
        creds = flow.run_local_server(
            port=8080,
            prompt="consent",
            access_type="offline",
        )
    except Exception as e:
        print(f"\nOAuth authorization failed: {e}")
        sys.exit(1)

    if not creds.refresh_token:
        print("\n[WARNING] No refresh token received.")
        print("Make sure you passed access_type='offline' and prompt='consent'.")
        print("You can revoke app permissions in your Google Account security settings and retry.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(" SUCCESS! Your YouTube Refresh Token has been generated.")
    print("=" * 60)
    print(f"\nYT_REFRESH_TOKEN={creds.refresh_token}\n")
    print("Next steps:")
    print("1. Add this to your local .env file:")
    print(f"   YT_REFRESH_TOKEN={creds.refresh_token}")
    print("2. Add it to GitHub Repository Secrets as YT_REFRESH_TOKEN")
    print("3. Keep this token secret. Never commit it to git.")
    print("=" * 60)


if __name__ == "__main__":
    main()

