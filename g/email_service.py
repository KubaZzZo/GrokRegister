"""TempMail.lol email service wrapper."""

import os
from typing import Any, Dict

from curl_cffi import requests
from dotenv import load_dotenv

TEMPMAIL_BASE = "https://api.tempmail.lol/v2"

load_dotenv()


def _tempmail_headers(api_key: str = "") -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


class EmailService:
    """TempMail.lol inbox creation and message polling."""

    def __init__(self, proxies: Any = None):
        self.proxies = proxies
        self.api_key = os.getenv("TEMPMAIL_LOL_API_KEY", "").strip()

    def create_email(self):
        """Create a random TempMail.lol inbox and return (token, email)."""
        try:
            response = requests.post(
                f"{TEMPMAIL_BASE}/inbox/create",
                headers=_tempmail_headers(self.api_key),
                json={"domain": None, "prefix": None},
                proxies=self.proxies,
                impersonate="chrome",
                timeout=15,
            )
            if response.status_code not in (200, 201):
                print(f"[error] TempMail.lol inbox creation failed: {response.status_code}")
                return None, None

            data = response.json()
            token = str(data.get("token") or "").strip()
            address = str(data.get("address") or "").strip()
            if token and address:
                return token, address

            print("[error] TempMail.lol inbox response did not include token/address")
            return None, None
        except Exception as e:
            print(f"[error] TempMail.lol request failed: {e}")
            return None, None

    def fetch_first_email(self, token):
        """Poll the inbox and return joined subject/body/html content."""
        try:
            response = requests.get(
                f"{TEMPMAIL_BASE}/inbox?token={token}",
                headers=_tempmail_headers(self.api_key),
                proxies=self.proxies,
                impersonate="chrome",
                timeout=15,
            )
            if response.status_code != 200:
                return None

            data = response.json()
            emails = data.get("emails") or []
            if not emails:
                return None

            message = emails[0]
            subject = str(message.get("subject") or "")
            body = str(message.get("body") or "")
            html = message.get("html") or ""
            if isinstance(html, list):
                html = "\n".join(str(item) for item in html)
            return "\n".join([subject, body, str(html)])
        except Exception as e:
            print(f"Failed to fetch email: {e}")
            return None
