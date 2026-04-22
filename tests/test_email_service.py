import importlib
import os
import sys
import types


def _install_curl_cffi_stub():
    curl_cffi_module = types.ModuleType("curl_cffi")
    curl_cffi_module.requests = types.SimpleNamespace()
    sys.modules["curl_cffi"] = curl_cffi_module


def test_create_email_returns_tempmail_token_and_address(monkeypatch):
    _install_curl_cffi_stub()
    monkeypatch.setenv("TEMPMAIL_LOL_API_KEY", "tm.test-key")
    sys.modules.pop("g", None)
    sys.modules.pop("g.email_service", None)

    import g.email_service as email_service

    email_service = importlib.reload(email_service)

    captured = {}

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url, headers=None, json=None, proxies=None, impersonate=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse(201, {"address": "abc@fake.tempmail.lol", "token": "tok-123"})

    monkeypatch.setattr(email_service.requests, "post", fake_post, raising=False)

    token, email = email_service.EmailService().create_email()

    assert token == "tok-123"
    assert email == "abc@fake.tempmail.lol"
    assert captured["url"].endswith("/inbox/create")
    assert captured["headers"]["Authorization"] == "Bearer tm.test-key"
    assert captured["json"] == {"domain": None, "prefix": None}


def test_fetch_first_email_returns_joined_tempmail_content(monkeypatch):
    _install_curl_cffi_stub()
    monkeypatch.delenv("TEMPMAIL_LOL_API_KEY", raising=False)
    sys.modules.pop("g", None)
    sys.modules.pop("g.email_service", None)

    import g.email_service as email_service

    email_service = importlib.reload(email_service)

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, headers=None, proxies=None, impersonate=None, timeout=None):
        assert url.endswith("/inbox?token=tok-123")
        return FakeResponse(
            200,
            {
                "expired": False,
                "emails": [
                    {
                        "from": "sender@example.com",
                        "to": "abc@fake.tempmail.lol",
                        "subject": "Verify",
                        "body": "Your code is 123456",
                        "html": "<b>123456</b>",
                        "date": 1710000000000,
                    }
                ],
            },
        )

    monkeypatch.setattr(email_service.requests, "get", fake_get, raising=False)

    content = email_service.EmailService().fetch_first_email("tok-123")

    assert "Verify" in content
    assert "Your code is 123456" in content
    assert "<b>123456</b>" in content
