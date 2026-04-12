"""One-time helper to obtain a Gmail OAuth2 refresh token.

Prerequisites:
  1. Go to https://console.cloud.google.com
  2. Create a project (or select existing)
  3. Enable the Gmail API (APIs & Services > Enable APIs)
  4. Create OAuth2 credentials:
     - APIs & Services > Credentials > Create Credentials
     - Choose "OAuth client ID"
     - Application type: "Desktop app"
     - Download the JSON or note the client_id / client_secret
  5. Configure OAuth consent screen:
     - Add yourself as a test user
     - Add scopes: gmail.modify, gmail.send

Usage:
  pip install requests
  python get_gmail_token.py
"""
import http.server
import json
import sys
import threading
import urllib.parse
import webbrowser

import requests

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
REDIRECT_URI = "http://localhost:8085"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def main():
    client_id = input("Enter your Google OAuth2 Client ID: ").strip()
    client_secret = input(
        "Enter your Google OAuth2 Client Secret: "
    ).strip()

    if not client_id or not client_secret:
        print("Both client_id and client_secret are required.")
        sys.exit(1)

    # Build authorization URL
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    # Capture the authorization code via local HTTP server
    code_holder = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query
            )
            code_holder["code"] = qs.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h1>Success! You can close this tab.</h1>"
            )

        def log_message(self, format, *args):
            pass  # suppress logs

    server = http.server.HTTPServer(("127.0.0.1", 8085), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    print("\nOpening browser for Google sign-in...\n")
    webbrowser.open(auth_url)

    thread.join(timeout=120)
    server.server_close()

    code = code_holder.get("code")
    if not code:
        print("ERROR: Did not receive authorization code.")
        sys.exit(1)

    # Exchange code for tokens
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, timeout=30)

    if not resp.ok:
        print(f"Token exchange failed: {resp.text}")
        sys.exit(1)

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        print("ERROR: No refresh_token in response.")
        print(json.dumps(tokens, indent=2))
        sys.exit(1)

    print("\n" + "=" * 50)
    print("SUCCESS! Add these as GitHub Secrets:\n")
    print(f"  GMAIL_CLIENT_ID     = {client_id}")
    print(f"  GMAIL_CLIENT_SECRET = {client_secret}")
    print(f"  GMAIL_REFRESH_TOKEN = {refresh_token}")
    print("=" * 50)


if __name__ == "__main__":
    main()
