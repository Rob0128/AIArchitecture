"""Gmail API client using OAuth2 refresh token.
Scopes: gmail.modify + gmail.send.
gmail.modify allows read and label changes but NOT delete.
gmail.send allows sending and replying."""
import base64
import logging
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailClient:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._token = None

    def _get_token(self):
        resp = requests.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }, timeout=30)
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    @property
    def headers(self):
        token = self._token or self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 30)
        resp = method(url, headers=self.headers, **kwargs)
        if resp.status_code == 401:
            self._get_token()
            resp = method(
                url, headers=self.headers, **kwargs
            )
        return resp

    def get_unread_emails(self, max_results=10):
        """List unread message IDs."""
        url = f"{GMAIL_BASE}/users/me/messages"
        params = {
            "q": "is:unread",
            "maxResults": max_results,
        }
        resp = self._request(
            requests.get, url, params=params
        )
        if resp.ok:
            return resp.json().get("messages", [])
        logger.error(
            "Failed to list emails: %s %s",
            resp.status_code, resp.text,
        )
        return []

    def _extract_body(self, payload):
        """Recursively extract plain-text body from
        Gmail payload."""
        body_data = (
            payload.get("body", {}).get("data", "")
        )
        if body_data:
            return base64.urlsafe_b64decode(
                body_data
            ).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                data = (
                    part.get("body", {}).get("data", "")
                )
                if data:
                    return base64.urlsafe_b64decode(
                        data
                    ).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            nested = self._extract_body(part)
            if nested:
                return nested

        return ""

    def get_email(self, message_id):
        """Get email and return normalised dict compatible
        with the orchestrator's extraction logic."""
        url = (
            f"{GMAIL_BASE}/users/me/messages/{message_id}"
        )
        resp = self._request(
            requests.get, url, params={"format": "full"}
        )
        if not resp.ok:
            logger.error(
                "Failed to get email %s: %s",
                message_id, resp.status_code,
            )
            return None

        raw = resp.json()
        headers = {
            h["name"]: h["value"]
            for h in raw.get("payload", {})
            .get("headers", [])
        }
        body = self._extract_body(
            raw.get("payload", {})
        )

        return {
            "id": raw.get("id"),
            "subject": headers.get("Subject", ""),
            "body": {"content": body},
            "from": {
                "emailAddress": {
                    "address": headers.get("From", ""),
                }
            },
        }

    def mark_as_read(self, message_id):
        """Remove UNREAD label (requires gmail.modify)."""
        url = (
            f"{GMAIL_BASE}/users/me/messages/"
            f"{message_id}/modify"
        )
        payload = {"removeLabelIds": ["UNREAD"]}
        resp = self._request(
            requests.post, url, json=payload
        )
        return resp.ok

    def reply_to_email(self, message_id, body_html):
        """Reply to an email in its thread."""
        url = (
            f"{GMAIL_BASE}/users/me/messages/{message_id}"
        )
        resp = self._request(
            requests.get, url, params={"format": "full"}
        )
        if not resp.ok:
            return False

        raw = resp.json()
        headers = {
            h["name"]: h["value"]
            for h in raw.get("payload", {})
            .get("headers", [])
        }
        to = headers.get("From", "")
        subject = headers.get("Subject", "")
        if not subject.startswith("Re: "):
            subject = f"Re: {subject}"
        thread_id = raw.get("threadId", "")
        msg_id_header = headers.get("Message-Id", "")

        mime = MIMEText(body_html, "html")
        mime["to"] = to
        mime["subject"] = subject
        if msg_id_header:
            mime["In-Reply-To"] = msg_id_header
            mime["References"] = msg_id_header

        encoded = base64.urlsafe_b64encode(
            mime.as_bytes()
        ).decode()
        send_url = f"{GMAIL_BASE}/users/me/messages/send"
        payload = {"raw": encoded, "threadId": thread_id}
        resp = self._request(
            requests.post, send_url, json=payload
        )
        return resp.ok

    def send_email(self, to, subject, body_html):
        """Send a new email."""
        mime = MIMEText(body_html, "html")
        mime["to"] = to
        mime["subject"] = subject

        encoded = base64.urlsafe_b64encode(
            mime.as_bytes()
        ).decode()
        url = f"{GMAIL_BASE}/users/me/messages/send"
        payload = {"raw": encoded}
        resp = self._request(
            requests.post, url, json=payload
        )
        return resp.ok
