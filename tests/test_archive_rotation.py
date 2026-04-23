import sys
import types
from pathlib import Path

import pytest


def _install_import_stubs():
    curl_cffi_module = types.ModuleType("curl_cffi")
    curl_cffi_module.requests = object()
    sys.modules.setdefault("curl_cffi", curl_cffi_module)

    bs4_module = types.ModuleType("bs4")

    class _BeautifulSoup:
        def __init__(self, *_args, **_kwargs):
            pass

        def find_all(self, *_args, **_kwargs):
            return []

    bs4_module.BeautifulSoup = _BeautifulSoup
    sys.modules.setdefault("bs4", bs4_module)

    g_module = types.ModuleType("g")
    g_module.EmailService = object
    g_module.TurnstileService = object
    g_module.__path__ = []
    sys.modules.setdefault("g", g_module)

    patchright_module = types.ModuleType("patchright")
    patchright_async_api_module = types.ModuleType("patchright.async_api")
    patchright_async_api_module.async_playwright = object()
    patchright_module.async_api = patchright_async_api_module
    sys.modules.setdefault("patchright", patchright_module)
    sys.modules.setdefault("patchright.async_api", patchright_async_api_module)


_install_import_stubs()

from grok import archive_result_files, latest_archive_files, list_archive_snapshots, read_accounts_file, read_sso_file
from webui import create_webui_app


def test_is_account_usable_rejects_accept_tos_redirect():
    import grok

    class _FakeResponse:
        def __init__(self, url, text=""):
            self.url = url
            self.text = text
            self.status_code = 200

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = types.SimpleNamespace(set=lambda *a, **k: None)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, timeout=0, allow_redirects=True):
            return _FakeResponse("https://accounts.x.ai/accept-tos", "Accept Terms of Service")

    grok.requests = types.SimpleNamespace(Session=_FakeSession)

    usable, reason = grok.is_account_usable("fake-sso")

    assert usable is False
    assert reason == "accept_tos_required"


def test_is_account_usable_accepts_non_tos_account_page():
    import grok

    class _FakeResponse:
        def __init__(self, url, text=""):
            self.url = url
            self.text = text
            self.status_code = 200

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = types.SimpleNamespace(set=lambda *a, **k: None)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, timeout=0, allow_redirects=True):
            return _FakeResponse("https://accounts.x.ai/", "Account home")

    grok.requests = types.SimpleNamespace(Session=_FakeSession)

    usable, reason = grok.is_account_usable("fake-sso")

    assert usable is True
    assert reason == "ok"


def test_extract_tos_acceptance_details_from_page_uses_transport_metadata():
    import grok

    html = '''
    <html><head></head><body>
    <script src="/_next/static/chunks/0r1wcrz2fx0ns.js"></script>
    <script src="/_next/static/chunks/other.js"></script>
    </body></html>
    '''
    js_map = {
        "https://accounts.x.ai/_next/static/chunks/0r1wcrz2fx0ns.js": '...setTosAcceptedVersion...q({tosVersion:c.TOS_ACCEPTED_VERSION},{onSuccess:b})...TOS_ACCEPTED_VERSION",0,1...',
        "https://accounts.x.ai/_next/static/chunks/other.js": 'nothing',
    }

    class _FakeResponse:
        def __init__(self, text):
            self.text = text

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = types.SimpleNamespace(set=lambda *a, **k: None)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, timeout=0, allow_redirects=True):
            return _FakeResponse(js_map[url])

    grok.requests = types.SimpleNamespace(Session=_FakeSession)

    details = grok.extract_tos_acceptance_details_from_page(html)

    assert details["tos_version"] == 1
    assert details["script_url"].endswith("0r1wcrz2fx0ns.js")


def test_extract_tos_acceptance_details_from_page_falls_back_when_not_found():
    import grok

    html = '<html><body><script src="/_next/static/chunks/other.js"></script></body></html>'

    class _FakeResponse:
        def __init__(self, text):
            self.text = text

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = types.SimpleNamespace(set=lambda *a, **k: None)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, timeout=0, allow_redirects=True):
            return _FakeResponse('console.log("noop")')

    grok.requests = types.SimpleNamespace(Session=_FakeSession)

    details = grok.extract_tos_acceptance_details_from_page(html)

    assert details["tos_version"] == 1
    assert details["script_url"] is None


def test_encode_set_tos_accepted_version_request_uses_field_two_int32():
    import grok

    payload = grok.encode_set_tos_accepted_version_request(1)

    assert payload == b"\x00\x00\x00\x00\x02\x10\x01"


def test_complete_tos_in_browser_context_returns_false_when_page_stays_on_accept_tos(monkeypatch):
    import grok

    class _FakePage:
        def __init__(self):
            self.url = "https://accounts.x.ai/accept-tos"
            self.clicked = []
            self.scripts = []

        async def goto(self, url, wait_until=None, timeout=None):
            self.url = url

        async def click(self, selector, timeout=None):
            self.clicked.append(selector)

        async def evaluate(self, script):
            self.scripts.append(script)
            return False

        async def wait_for_timeout(self, ms):
            return None

    class _FakeContext:
        def __init__(self):
            self.cookies = None
            self.page = _FakePage()

        async def add_cookies(self, cookies):
            self.cookies = cookies

        async def new_page(self):
            return self.page

        async def close(self):
            return None

    class _FakeBrowser:
        def __init__(self):
            self.context = _FakeContext()

        async def new_context(self, **kwargs):
            return self.context

        async def close(self):
            return None

    class _FakePlaywright:
        def __init__(self):
            self.chromium = self
            self.browser = _FakeBrowser()

        async def launch(self, **kwargs):
            return self.browser

        async def start(self):
            return self

        async def stop(self):
            return None

    monkeypatch.setattr(grok, "async_playwright", lambda: _FakePlaywright())

    success, reason = grok.run_async(grok.complete_tos_in_browser_context("fake-sso"))

    assert success is False
    assert reason == "accept_tos_required"


def test_complete_tos_in_browser_context_uses_dom_fallback_when_click_fails(monkeypatch):
    import grok

    class _FakePage:
        def __init__(self):
            self.url = "https://accounts.x.ai/"
            self.clicked = []
            self.scripts = []

        async def goto(self, url, wait_until=None, timeout=None):
            self.url = url

        async def click(self, selector, timeout=None):
            self.clicked.append(selector)
            raise Exception("selector failed")

        async def evaluate(self, script):
            self.scripts.append(script)
            return True

        async def wait_for_timeout(self, ms):
            return None

    class _FakeContext:
        def __init__(self):
            self.page = _FakePage()

        async def add_cookies(self, cookies):
            return None

        async def new_page(self):
            return self.page

        async def close(self):
            return None

    class _FakeBrowser:
        async def new_context(self, **kwargs):
            return _FakeContext()

        async def close(self):
            return None

    class _FakePlaywright:
        def __init__(self):
            self.chromium = self

        async def launch(self, **kwargs):
            return _FakeBrowser()

        async def start(self):
            return self

        async def stop(self):
            return None

    monkeypatch.setattr(grok, "async_playwright", lambda: _FakePlaywright())

    success, reason = grok.run_async(grok.complete_tos_in_browser_context("fake-sso"))

    assert success is False
    assert reason == "accept_tos_required"


def test_complete_signup_in_browser_context_returns_cloudflare_blocked_when_signup_page_is_blocked(monkeypatch):
    import grok

    class _FakePage:
        def __init__(self):
            self.url = "https://accounts.x.ai/sign-up"

        async def goto(self, url, wait_until=None, timeout=None):
            self.url = url

        async def wait_for_timeout(self, ms):
            return None

        async def title(self):
            return "Attention Required! | Cloudflare"

        async def content(self):
            return "<div id='cf-error-details'>Sorry, you have been blocked</div>"

        async def evaluate(self, script, arg=None):
            return None

    class _FakeContext:
        def __init__(self):
            self.page = _FakePage()
            self.init_scripts = []

        async def new_page(self):
            return self.page

        async def add_init_script(self, script):
            self.init_scripts.append(script)

        async def close(self):
            return None

    class _FakeBrowser:
        def __init__(self):
            self.context = _FakeContext()

        async def new_context(self, **kwargs):
            return self.context

        async def close(self):
            return None

    class _FakePlaywright:
        def __init__(self):
            self.chromium = self
            self.browser = _FakeBrowser()

        async def launch(self, **kwargs):
            return self.browser

        async def start(self):
            return self

        async def stop(self):
            return None

    monkeypatch.setattr(grok, "async_playwright", lambda: _FakePlaywright())

    success, reason, sso = grok.run_async(
        grok.complete_signup_in_browser_context("user@example.com", "pass123", "ABC123", "token")
    )

    assert success is False
    assert reason == "cloudflare_blocked"
    assert sso == ""


def test_complete_signup_in_browser_context_extracts_sso_from_context_cookies(monkeypatch):
    import grok

    class _FakePage:
        def __init__(self):
            self.gotos = []
            self.clicks = []
            self.fills = []
            self.url = "https://accounts.x.ai/"

        async def goto(self, url, wait_until=None, timeout=None):
            self.gotos.append((url, wait_until, timeout))

        async def click(self, selector, timeout=None):
            self.clicks.append(selector)
            if selector in {
                'button:has-text("Reject All")',
                'button:has-text("Confirm My Choices")',
                'button:has-text("Allow All")',
                'button:has-text("Sign up with email")',
                'button[type="submit"]',
            }:
                return None
            raise Exception("not found")

        async def fill(self, selector, value, timeout=None):
            self.fills.append((selector, value))
            if selector in {
                'input[type="email"]',
                'input[type="password"]',
                'input[name*="code" i]',
            }:
                return None
            raise Exception("not found")

        async def wait_for_timeout(self, ms):
            return None

        async def content(self):
            return ""

    class _FakeContext:
        def __init__(self):
            self.page = _FakePage()

        async def new_page(self):
            return self.page

        async def cookies(self):
            return [
                {"name": "cf_clearance", "value": "ignore-me"},
                {"name": "sso", "value": "sso-from-cookie-store"},
            ]

        async def storage_state(self):
            return {}

        async def close(self):
            return None

    class _FakeBrowser:
        def __init__(self):
            self.context = _FakeContext()

        async def new_context(self, **kwargs):
            return self.context

        async def close(self):
            return None

    class _FakePlaywright:
        def __init__(self):
            self.chromium = self
            self.browser = _FakeBrowser()

        async def launch(self, **kwargs):
            return self.browser

        async def start(self):
            return self

        async def stop(self):
            return None

    monkeypatch.setattr(grok, "async_playwright", lambda: _FakePlaywright())

    success, reason, sso = grok.run_async(
        grok.complete_signup_in_browser_context("user@example.com", "pass123", "ABC123", "token")
    )

    assert success is True
    assert reason == "ok"
    assert sso == "sso-from-cookie-store"


def test_complete_signup_in_browser_context_follows_bootstrap_url_for_sso(monkeypatch):
    import grok

    class _FakePage:
        def __init__(self, context):
            self.context = context
            self.gotos = []
            self.clicks = []
            self.fills = []
            self.url = "https://accounts.x.ai/post-submit"

        async def goto(self, url, wait_until=None, timeout=None):
            self.gotos.append((url, wait_until, timeout))
            if "set-cookie?q=" in url:
                self.context.bootstrap_followed = True
                self.url = "https://accounts.x.ai/"
                return None
            self.url = url

        async def click(self, selector, timeout=None):
            self.clicks.append(selector)
            if selector in {
                'button:has-text("Reject All")',
                'button:has-text("Confirm My Choices")',
                'button:has-text("Allow All")',
                'button:has-text("Sign up with email")',
                'button[type="submit"]',
            }:
                return None
            raise Exception("not found")

        async def fill(self, selector, value, timeout=None):
            self.fills.append((selector, value))
            if selector in {
                'input[type="email"]',
                'input[type="password"]',
                'input[name*="code" i]',
            }:
                return None
            raise Exception("not found")

        async def wait_for_timeout(self, ms):
            return None

        async def content(self):
            return 'prefix https://accounts.x.ai/set-cookie?q=bootstrap-token1: suffix'

    class _FakeContext:
        def __init__(self):
            self.bootstrap_followed = False
            self.page = _FakePage(self)

        async def new_page(self):
            return self.page

        async def cookies(self):
            if self.bootstrap_followed:
                return [{"name": "sso", "value": "sso-from-bootstrap"}]
            return []

        async def storage_state(self):
            return {}

        async def close(self):
            return None

    class _FakeBrowser:
        def __init__(self):
            self.context = _FakeContext()

        async def new_context(self, **kwargs):
            return self.context

        async def close(self):
            return None

    class _FakePlaywright:
        def __init__(self):
            self.chromium = self
            self.browser = _FakeBrowser()

        async def launch(self, **kwargs):
            return self.browser

        async def start(self):
            return self

        async def stop(self):
            return None

    monkeypatch.setattr(grok, "async_playwright", lambda: _FakePlaywright())

    success, reason, sso = grok.run_async(
        grok.complete_signup_in_browser_context("user@example.com", "pass123", "ABC123", "token")
    )

    assert success is True
    assert reason == "ok"
    assert sso == "sso-from-bootstrap"


def test_complete_signup_in_browser_context_uses_storage_state_when_cookie_store_is_empty(monkeypatch):
    import grok

    class _FakePage:
        def __init__(self):
            self.url = "https://accounts.x.ai/"

        async def goto(self, url, wait_until=None, timeout=None):
            self.url = url

        async def click(self, selector, timeout=None):
            if selector in {
                'button:has-text("Reject All")',
                'button:has-text("Confirm My Choices")',
                'button:has-text("Allow All")',
                'button:has-text("Sign up with email")',
                'button[type="submit"]',
            }:
                return None
            raise Exception("not found")

        async def fill(self, selector, value, timeout=None):
            if selector in {
                'input[type="email"]',
                'input[type="password"]',
                'input[name*="code" i]',
            }:
                return None
            raise Exception("not found")

        async def wait_for_timeout(self, ms):
            return None

        async def content(self):
            return ""

    class _FakeContext:
        def __init__(self):
            self.page = _FakePage()

        async def new_page(self):
            return self.page

        async def cookies(self):
            return []

        async def storage_state(self):
            return {"cookies": [], "origins": [{"localStorage": [{"name": "sso", "value": "sso-from-storage"}]}]}

        async def close(self):
            return None

    class _FakeBrowser:
        def __init__(self):
            self.context = _FakeContext()

        async def new_context(self, **kwargs):
            return self.context

        async def close(self):
            return None

    class _FakePlaywright:
        def __init__(self):
            self.chromium = self
            self.browser = _FakeBrowser()

        async def launch(self, **kwargs):
            return self.browser

        async def start(self):
            return self

        async def stop(self):
            return None

    monkeypatch.setattr(grok, "async_playwright", lambda: _FakePlaywright())

    success, reason, sso = grok.run_async(
        grok.complete_signup_in_browser_context("user@example.com", "pass123", "ABC123", "token")
    )

    assert success is True
    assert reason == "ok"
    assert sso == "sso-from-storage"


def test_complete_signup_in_browser_context_uses_submit_response_bootstrap_url(monkeypatch):
    import grok

    class _FakeResponse:
        def __init__(self, text):
            self.request = types.SimpleNamespace(method="POST")
            self._text = text

        def text(self):
            return self._text

    class _FakeExpectResponse:
        def __init__(self, response):
            self.value = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakePage:
        def __init__(self, context):
            self.context = context
            self.url = "https://accounts.x.ai/post-submit"

        async def goto(self, url, wait_until=None, timeout=None):
            if "set-cookie?q=" in url:
                self.context.bootstrap_followed = True
                self.url = "https://accounts.x.ai/"
                return None
            self.url = url

        async def click(self, selector, timeout=None):
            if selector in {
                'button:has-text("Reject All")',
                'button:has-text("Confirm My Choices")',
                'button:has-text("Allow All")',
                'button:has-text("Sign up with email")',
                'button[type="submit"]',
            }:
                return None
            raise Exception("not found")

        async def fill(self, selector, value, timeout=None):
            if selector in {
                'input[type="email"]',
                'input[type="password"]',
                'input[name*="code" i]',
            }:
                return None
            raise Exception("not found")

        def expect_response(self, predicate, timeout=None):
            response = _FakeResponse('prefix https://accounts.x.ai/set-cookie?q=response-token suffix')
            assert predicate(response) is True
            return _FakeExpectResponse(response)

        async def wait_for_timeout(self, ms):
            return None

        async def content(self):
            return ""

    class _FakeContext:
        def __init__(self):
            self.bootstrap_followed = False
            self.page = _FakePage(self)

        async def new_page(self):
            return self.page

        async def cookies(self):
            if self.bootstrap_followed:
                return [{"name": "sso", "value": "sso-from-submit-response"}]
            return []

        async def storage_state(self):
            return {}

        async def close(self):
            return None

    class _FakeBrowser:
        def __init__(self):
            self.context = _FakeContext()

        async def new_context(self, **kwargs):
            return self.context

        async def close(self):
            return None

    class _FakePlaywright:
        def __init__(self):
            self.chromium = self
            self.browser = _FakeBrowser()

        async def launch(self, **kwargs):
            return self.browser

        async def start(self):
            return self

        async def stop(self):
            return None

    monkeypatch.setattr(grok, "async_playwright", lambda: _FakePlaywright())

    success, reason, sso = grok.run_async(
        grok.complete_signup_in_browser_context("user@example.com", "pass123", "ABC123", "token")
    )

    assert success is True
    assert reason == "ok"
    assert sso == "sso-from-submit-response"


def test_register_single_thread_tries_multiple_action_ids_after_server_action_not_found(monkeypatch, tmp_path):
    import grok

    class FakeEmailService:
        def __init__(self, proxies=None):
            pass

        def create_email(self):
            return "jwt", "user@example.com"

        def fetch_first_email(self, jwt):
            return ">ABC-123<"

    class FakeTurnstileService:
        def create_task(self, siteurl, sitekey):
            return "task-1"

        def get_response(self, task_id, max_retries=30, initial_delay=5, retry_delay=2):
            return "token-ok"

    class FakeCookies:
        def __init__(self):
            self.sso = None

        def get(self, key, default=None, domain=None):
            if key == "sso":
                return self.sso or default
            return default

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = FakeCookies()
            self.post_calls = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, *args, **kwargs):
            if "set-cookie?q=" in url:
                self.cookies.sso = "sso-from-second-action"
            return types.SimpleNamespace(url="https://accounts.x.ai/", text="ok")

        def post(self, url, json=None, headers=None, **kwargs):
            self.post_calls.append(headers.get("next-action"))
            if len(self.post_calls) == 1:
                return types.SimpleNamespace(status_code=404, text="Server action not found.")
            return types.SimpleNamespace(status_code=200, text='https://accounts.x.ai/set-cookie?q=bootstrap1:')

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(grok, "EmailService", FakeEmailService)
    monkeypatch.setattr(grok, "TurnstileService", FakeTurnstileService)
    monkeypatch.setattr(grok, "requests", types.SimpleNamespace(Session=FakeSession))
    monkeypatch.setattr(grok, "send_email_code_grpc", lambda session, email: True)
    monkeypatch.setattr(grok, "verify_email_code_grpc", lambda session, email, code: True)
    monkeypatch.setattr(grok.time, "sleep", lambda *_: None)
    monkeypatch.setattr(grok, "is_account_usable", lambda sso: (True, "ok"))

    grok.PROXIES = {}
    grok.config["site_key"] = "sitekey"
    grok.config["state_tree"] = "tree"
    grok.config["action_id"] = "action-1"
    grok.config["action_ids"] = ["action-1", "action-2"]
    grok.stop_event.clear()
    grok.success_count = 0
    grok.runtime_state["success_count"] = 0
    grok.start_time = 1

    grok.register_single_thread()

    accounts_path = tmp_path / "keys" / "accounts.txt"
    assert accounts_path.exists()
    content = accounts_path.read_text(encoding="utf-8")
    assert "sso-from-second-action" in content


def test_register_single_thread_prefers_browser_signup_flow_when_requests_session_bootstrap_missing(monkeypatch, tmp_path):
    import grok

    class FakeEmailService:
        def __init__(self, proxies=None):
            pass

        def create_email(self):
            return "jwt", "user@example.com"

        def fetch_first_email(self, jwt):
            return ">ABC-123<"

    class FakeTurnstileService:
        def create_task(self, siteurl, sitekey):
            return "task-1"

        def get_response(self, task_id, max_retries=30, initial_delay=5, retry_delay=2):
            return "token-ok"

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = types.SimpleNamespace(get=lambda key, default=None, domain=None: default)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return types.SimpleNamespace(url="https://accounts.x.ai/", text="ok")

        def post(self, *args, **kwargs):
            return types.SimpleNamespace(status_code=200, text="{}")

    browser_calls = []

    def fake_browser_signup(email, password, verify_code, token):
        browser_calls.append((email, password, verify_code, token))
        return True, "ok", "sso-browser"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(grok, "EmailService", FakeEmailService)
    monkeypatch.setattr(grok, "TurnstileService", FakeTurnstileService)
    monkeypatch.setattr(grok, "requests", types.SimpleNamespace(Session=FakeSession))
    monkeypatch.setattr(grok, "send_email_code_grpc", lambda session, email: True)
    monkeypatch.setattr(grok, "verify_email_code_grpc", lambda session, email, code: True)
    monkeypatch.setattr(grok.time, "sleep", lambda *_: None)
    monkeypatch.setattr(grok, "complete_signup_in_browser_context", fake_browser_signup)
    monkeypatch.setattr(grok, "is_account_usable", lambda sso: (True, "ok"))

    grok.PROXIES = {}
    grok.config["action_id"] = "action"
    grok.config["site_key"] = "sitekey"
    grok.stop_event.clear()
    grok.success_count = 0
    grok.runtime_state["success_count"] = 0
    grok.start_time = 1

    grok.register_single_thread()

    assert browser_calls
    accounts_path = tmp_path / "keys" / "accounts.txt"
    assert accounts_path.exists()
    assert "sso-browser" in accounts_path.read_text(encoding="utf-8")


def test_register_single_thread_handles_empty_json_signup_response(monkeypatch, tmp_path):
    import grok

    class FakeEmailService:
        def __init__(self, proxies=None):
            pass

        def create_email(self):
            return "jwt", "user@example.com"

        def fetch_first_email(self, jwt):
            return ">ABC-123<"

    class FakeTurnstileService:
        def create_task(self, siteurl, sitekey):
            return "task-1"

        def get_response(self, task_id, max_retries=30, initial_delay=5, retry_delay=2):
            return "token-ok"

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = types.SimpleNamespace(get=lambda key, default=None, domain=None: default)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return types.SimpleNamespace(url="https://accounts.x.ai/", text="ok")

        def post(self, *args, **kwargs):
            grok.stop_event.set()
            return types.SimpleNamespace(status_code=200, text="{}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(grok, "EmailService", FakeEmailService)
    monkeypatch.setattr(grok, "TurnstileService", FakeTurnstileService)
    monkeypatch.setattr(grok, "requests", types.SimpleNamespace(Session=FakeSession))
    monkeypatch.setattr(grok, "send_email_code_grpc", lambda session, email: True)
    monkeypatch.setattr(grok, "verify_email_code_grpc", lambda session, email, code: True)
    monkeypatch.setattr(grok.time, "sleep", lambda *_: None)

    grok.PROXIES = {}
    grok.config["action_id"] = "action"
    grok.config["site_key"] = "sitekey"
    grok.stop_event.clear()

    grok.register_single_thread()

    assert grok.runtime_state["last_error"] is None
    assert not (tmp_path / "keys" / "accounts.txt").exists()


def test_register_single_thread_uses_domain_scoped_cf_bm_cookie(monkeypatch, tmp_path):
    import grok

    class FakeEmailService:
        def __init__(self, proxies=None):
            pass

        def create_email(self):
            return "jwt", "user@example.com"

        def fetch_first_email(self, jwt):
            return ">ABC-123<"

    class FakeTurnstileService:
        def create_task(self, siteurl, sitekey):
            return "task-1"

        def get_response(self, task_id, max_retries=30, initial_delay=5, retry_delay=2):
            return "token-ok"

    class FakeCookies:
        def __init__(self):
            self.calls = []

        def get(self, key, default=None, domain=None):
            self.calls.append((key, domain))
            if key == "__cf_bm" and domain == ".x.ai":
                return "cf-token"
            if key == "sso":
                return None
            return default

    class FakeSession:
        instances = []

        def __init__(self, *args, **kwargs):
            self.cookies = FakeCookies()
            FakeSession.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return types.SimpleNamespace(url="https://accounts.x.ai/", text="ok")

        def post(self, *args, **kwargs):
            grok.stop_event.set()
            return types.SimpleNamespace(status_code=500, text="bad")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(grok, "EmailService", FakeEmailService)
    monkeypatch.setattr(grok, "TurnstileService", FakeTurnstileService)
    monkeypatch.setattr(grok, "requests", types.SimpleNamespace(Session=FakeSession))
    monkeypatch.setattr(grok, "send_email_code_grpc", lambda session, email: True)
    monkeypatch.setattr(grok, "verify_email_code_grpc", lambda session, email, code: True)
    monkeypatch.setattr(grok.time, "sleep", lambda *_: None)

    grok.PROXIES = {}
    grok.config["action_id"] = "action"
    grok.config["site_key"] = "sitekey"
    grok.stop_event.clear()

    grok.register_single_thread()

    assert FakeSession.instances
    assert ("__cf_bm", ".x.ai") in FakeSession.instances[0].cookies.calls


def test_register_single_thread_attempts_browser_tos_completion_before_rejecting_session(monkeypatch, tmp_path):
    import grok

    class FakeEmailService:
        def __init__(self, proxies=None):
            pass

        def create_email(self):
            return "jwt", "user@example.com"

        def fetch_first_email(self, jwt):
            return ">ABC-123<"

    class FakeTurnstileService:
        def create_task(self, siteurl, sitekey):
            return "task-1"

        def get_response(self, task_id, max_retries=30, initial_delay=5, retry_delay=2):
            return "token-ok"

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies_map = {"sso": "sso-123"}
            self.cookies = types.SimpleNamespace(
                get=lambda key, default=None: self.cookies_map.get(key, default)
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return types.SimpleNamespace(url="https://accounts.x.ai/accept-tos", text="Accept Terms of Service")

        def post(self, *args, **kwargs):
            return types.SimpleNamespace(
                status_code=200,
                text='https://accounts.x.ai/set-cookie?q=abc1:'
            )

    completion_calls = []
    usability_checks = []

    def fake_complete_tos(sso):
        completion_calls.append(sso)
        return True, "ok"

    def fake_is_usable(sso):
        usability_checks.append(sso)
        if len(usability_checks) == 1:
            return False, "accept_tos_required"
        grok.stop_event.set()
        return True, "ok"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(grok, "EmailService", FakeEmailService)
    monkeypatch.setattr(grok, "TurnstileService", FakeTurnstileService)
    monkeypatch.setattr(grok, "requests", types.SimpleNamespace(Session=FakeSession))
    monkeypatch.setattr(grok, "send_email_code_grpc", lambda session, email: True)
    monkeypatch.setattr(grok, "verify_email_code_grpc", lambda session, email, code: True)
    monkeypatch.setattr(grok.time, "sleep", lambda *_: None)
    monkeypatch.setattr(grok, "complete_tos_in_browser_context", lambda sso: (True, "ok"))
    monkeypatch.setattr(grok, "run_async", fake_complete_tos)
    monkeypatch.setattr(grok, "is_account_usable", fake_is_usable)

    grok.PROXIES = {}
    grok.config["action_id"] = "action"
    grok.config["site_key"] = "sitekey"
    grok.stop_event.clear()
    grok.success_count = 0
    grok.runtime_state["success_count"] = 0
    grok.start_time = 1

    grok.register_single_thread()

    assert completion_calls
    assert usability_checks == ["sso-123", "sso-123"]
    accounts_path = tmp_path / "keys" / "accounts.txt"
    assert accounts_path.exists()
    assert "user@example.com" in accounts_path.read_text(encoding="utf-8")


def test_archive_result_files_rotates_live_files_into_timestamped_archive(tmp_path: Path):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    (keys_dir / "accounts.txt").write_text("a:pwd:sso\n", encoding="utf-8")
    (keys_dir / "grok.txt").write_text("sso\n", encoding="utf-8")

    archived = archive_result_files(keys_dir)

    archive_dir = keys_dir / "archive"
    assert archive_dir.exists()
    assert not (keys_dir / "accounts.txt").exists()
    assert not (keys_dir / "grok.txt").exists()
    assert archived["accounts.txt"].exists()
    assert archived["grok.txt"].exists()
    assert archived["accounts.txt"].read_text(encoding="utf-8") == "a:pwd:sso\n"
    assert archived["grok.txt"].read_text(encoding="utf-8") == "sso\n"


def test_latest_archive_files_prefers_newest_archive(tmp_path: Path):
    keys_dir = tmp_path / "keys"
    archive_dir = keys_dir / "archive"
    archive_dir.mkdir(parents=True)
    older_accounts = archive_dir / "accounts-20260101-000000.txt"
    older_grok = archive_dir / "grok-20260101-000000.txt"
    newer_accounts = archive_dir / "accounts-20260102-000000.txt"
    newer_grok = archive_dir / "grok-20260102-000000.txt"
    older_accounts.write_text("old\n", encoding="utf-8")
    older_grok.write_text("old\n", encoding="utf-8")
    newer_accounts.write_text("new\n", encoding="utf-8")
    newer_grok.write_text("new\n", encoding="utf-8")

    latest = latest_archive_files(keys_dir)

    assert latest["accounts.txt"] == newer_accounts
    assert latest["grok.txt"] == newer_grok


def test_list_archive_snapshots_groups_accounts_and_grok_files(tmp_path: Path):
    keys_dir = tmp_path / "keys"
    archive_dir = keys_dir / "archive"
    archive_dir.mkdir(parents=True)
    accounts_new = archive_dir / "accounts-20260102-000000.txt"
    grok_new = archive_dir / "grok-20260102-000000.txt"
    accounts_old = archive_dir / "accounts-20260101-000000.txt"
    accounts_new.write_text("a\nb\n", encoding="utf-8")
    grok_new.write_text("g\n", encoding="utf-8")
    accounts_old.write_text("older\n", encoding="utf-8")

    snapshots = list_archive_snapshots(keys_dir)

    assert snapshots[0]["timestamp"] == "20260102-000000"
    assert snapshots[0]["files"]["accounts.txt"].name == "accounts-20260102-000000.txt"
    assert snapshots[0]["files"]["grok.txt"].name == "grok-20260102-000000.txt"
    assert snapshots[0]["counts"]["accounts.txt"] == 2
    assert snapshots[0]["counts"]["grok.txt"] == 1
    assert snapshots[1]["timestamp"] == "20260101-000000"
    assert snapshots[1]["counts"]["accounts.txt"] == 1


def test_readers_fall_back_to_latest_archive_when_live_files_missing(tmp_path: Path):
    keys_dir = tmp_path / "keys"
    archive_dir = keys_dir / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "accounts-20260102-000000.txt").write_text("a:pwd:sso\n", encoding="utf-8")
    (archive_dir / "grok-20260102-000000.txt").write_text("sso\n", encoding="utf-8")

    assert read_accounts_file(keys_dir) == ["a:pwd:sso"]
    assert read_sso_file(keys_dir) == ["sso"]


@pytest.mark.asyncio
async def test_ui_status_contains_live_accounts_and_choice_state(monkeypatch):
    app = create_webui_app(
        headless=True,
        useragent=None,
        debug=False,
        browser_type="chromium",
        thread=2,
        proxy_support=True,
    )
    app.config["TESTING"] = True
    app.config["SELECTED_NEXT_ACTION"] = "优先增加更好看的页面样式"

    monkeypatch.setattr("webui.grok.get_runtime_state", lambda: {
        "running": True,
        "thread_count": 3,
        "success_count": 8,
        "action_id": "action-123",
        "last_error": "",
    })
    monkeypatch.setattr("webui.grok.read_accounts_file", lambda: ["acc-1", "acc-2"])
    monkeypatch.setattr("webui.grok.read_sso_file", lambda: ["sso-1"])
    monkeypatch.setattr("webui.grok.list_archive_snapshots", lambda: [{
        "timestamp": "20260102-000000",
        "files": {"accounts.txt": Path("keys/archive/accounts-20260102-000000.txt")},
        "counts": {"accounts.txt": 2},
    }])

    test_client = app.test_client()
    response = await test_client.get("/api/ui/status")
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["running"] is True
    assert payload["accounts_count"] == 2
    assert payload["accounts"] == ["acc-1", "acc-2"]
    assert payload["sso_count"] == 1
    assert payload["selected_next_action"] == "优先增加更好看的页面样式"
    assert payload["archive_snapshots"][0]["files"]["accounts.txt"] == "accounts-20260102-000000.txt"


@pytest.mark.asyncio
async def test_ui_choice_persists_selected_option(monkeypatch):
    app = create_webui_app(
        headless=True,
        useragent=None,
        debug=False,
        browser_type="chromium",
        thread=2,
        proxy_support=True,
    )
    app.config["TESTING"] = True
    monkeypatch.setattr("webui.grok.get_runtime_state", lambda: {
        "running": False,
        "thread_count": 2,
        "success_count": 0,
        "action_id": None,
        "last_error": "",
    })
    monkeypatch.setattr("webui.grok.read_accounts_file", lambda: [])
    monkeypatch.setattr("webui.grok.read_sso_file", lambda: [])
    monkeypatch.setattr("webui.grok.list_archive_snapshots", lambda: [])

    test_client = app.test_client()
    response = await test_client.post("/ui/choice", form={"next_action": "继续做产品化增强"})
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["selected_next_action"] == "继续做产品化增强"

    status_resp = await test_client.get("/api/ui/status")
    status_payload = await status_resp.get_json()
    assert status_payload["selected_next_action"] == "继续做产品化增强"
