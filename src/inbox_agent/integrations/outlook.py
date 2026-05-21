import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests
import structlog

logger = structlog.get_logger()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTH_BASE = "https://login.microsoftonline.com"


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    body_preview: str
    body: str
    received_at: str
    has_attachments: bool


class OutlookClient:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str, token_path: Path):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_path = token_path
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: float = 0
        self._load_tokens()

    def _load_tokens(self):
        if self.token_path.exists():
            data = json.loads(self.token_path.read_text())
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            self._token_expiry = data.get("expiry", 0)

    def _save_tokens(self):
        self.token_path.write_text(json.dumps({
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expiry": self._token_expiry,
        }))

    def authenticate_device_code(self) -> bool:
        """Interactive device-code flow. Returns True on success."""
        url = f"{AUTH_BASE}/{self.tenant_id}/oauth2/v2.0/devicecode"
        resp = requests.post(url, data={
            "client_id": self.client_id,
            "scope": "Mail.Read Mail.ReadWrite offline_access",
        })
        resp.raise_for_status()
        data = resp.json()

        print(f"\n{'='*60}")
        print(f"To sign in, open: {data['verification_uri']}")
        print(f"Enter the code:  {data['user_code']}")
        print(f"{'='*60}\n")

        token_url = f"{AUTH_BASE}/{self.tenant_id}/oauth2/v2.0/token"
        interval = data.get("interval", 5)
        expires_at = time.time() + data["expires_in"]

        while time.time() < expires_at:
            time.sleep(interval)
            token_resp = requests.post(token_url, data={
                "grant_type": "urn:ietf:params:oauth2:grant-type:device_code",
                "client_id": self.client_id,
                "device_code": data["device_code"],
            })
            token_data = token_resp.json()

            if "access_token" in token_data:
                self._access_token = token_data["access_token"]
                self._refresh_token = token_data.get("refresh_token")
                self._token_expiry = time.time() + token_data.get("expires_in", 3600)
                self._save_tokens()
                logger.info("outlook_auth_success")
                return True

            if token_data.get("error") == "authorization_pending":
                continue
            if token_data.get("error") in ("authorization_declined", "expired_token", "bad_verification_code"):
                logger.error("outlook_auth_failed", error=token_data["error"])
                return False

        logger.error("outlook_auth_timeout")
        return False

    def _refresh_access_token(self):
        if not self._refresh_token:
            raise RuntimeError("No refresh token available. Run setup again.")

        url = f"{AUTH_BASE}/{self.tenant_id}/oauth2/v2.0/token"
        resp = requests.post(url, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
            "scope": "Mail.Read Mail.ReadWrite offline_access",
        })
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        self._save_tokens()

    def _get_headers(self) -> dict:
        if time.time() >= self._token_expiry - 60:
            self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def get_unread_emails(self, limit: int = 50) -> list[Email]:
        url = f"{GRAPH_BASE}/me/messages"
        params = {
            "$filter": "isRead eq false",
            "$top": limit,
            "$orderby": "receivedDateTime desc",
            "$select": "id,from,subject,bodyPreview,body,receivedDateTime,hasAttachments",
        }
        resp = requests.get(url, headers=self._get_headers(), params=params)
        resp.raise_for_status()

        emails = []
        for msg in resp.json().get("value", []):
            emails.append(Email(
                id=msg["id"],
                sender=msg["from"]["emailAddress"]["address"],
                subject=msg.get("subject", "(no subject)"),
                body_preview=msg.get("bodyPreview", ""),
                body=msg.get("body", {}).get("content", ""),
                received_at=msg["receivedDateTime"],
                has_attachments=msg.get("hasAttachments", False),
            ))
        return emails

    def mark_as_read(self, email_id: str):
        url = f"{GRAPH_BASE}/me/messages/{email_id}"
        resp = requests.patch(
            url,
            headers={**self._get_headers(), "Content-Type": "application/json"},
            json={"isRead": True},
        )
        resp.raise_for_status()
