from __future__ import annotations

import concurrent.futures
import glob
import os
import random
import re
import string
import struct
import threading
import time
import asyncio
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from patchright.async_api import async_playwright

from g import EmailService, TurnstileService

# Base configuration
site_url = "https://accounts.x.ai"
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
PROXIES = {}

# Values discovered dynamically from the signup page.
config = {
    "site_key": "0x4AAAAAAAhr9JGVDZbrZOo0",
    "action_id": None,
    "action_ids": [],
    "state_tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fsign-up%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
}

post_lock = threading.Lock()
file_lock = threading.Lock()
success_count = 0
start_time = time.time()
stop_event = threading.Event()
runtime_state = {
    "running": False,
    "thread_count": 0,
    "started_at": None,
    "last_error": None,
    "success_count": 0,
    "browser_trace": {},
}


def ensure_runtime_directories(base_path: str | Path = "keys") -> Path:
    runtime_dir = Path(base_path)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "archive").mkdir(parents=True, exist_ok=True)
    return runtime_dir


def latest_archive_files(base_path: str | Path = "keys") -> dict[str, Path]:
    runtime_dir = ensure_runtime_directories(base_path)
    archive_dir = runtime_dir / "archive"
    latest: dict[str, Path] = {}
    for name in ("accounts.txt", "grok.txt"):
        stem = Path(name).stem
        matches = sorted(archive_dir.glob(f"{stem}-*.txt"))
        if matches:
            latest[name] = matches[-1]
    return latest


def list_archive_snapshots(base_path: str | Path = "keys") -> list[dict]:
    runtime_dir = ensure_runtime_directories(base_path)
    archive_dir = runtime_dir / "archive"
    grouped: dict[str, dict[str, Path]] = {}
    for name in ("accounts", "grok"):
        for path in sorted(archive_dir.glob(f"{name}-*.txt")):
            timestamp = path.stem[len(name) + 1 :]
            grouped.setdefault(timestamp, {})[f"{name}.txt"] = path
    snapshots = []
    for timestamp, files in sorted(grouped.items(), reverse=True):
        counts = {}
        for name, path in files.items():
            counts[name] = len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
        snapshots.append({"timestamp": timestamp, "files": files, "counts": counts})
    return snapshots


def archive_result_files(base_path: str | Path = "keys") -> dict[str, Path]:
    runtime_dir = ensure_runtime_directories(base_path)
    archive_dir = runtime_dir / "archive"
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    archived: dict[str, Path] = {}
    for name in ("accounts.txt", "grok.txt"):
        source = runtime_dir / name
        if not source.exists():
            continue
        target = archive_dir / f"{Path(name).stem}-{timestamp}.txt"
        source.replace(target)
        archived[name] = target
    return archived


def _read_result_file(name: str, base_path: str | Path = "keys") -> list[str]:
    runtime_dir = ensure_runtime_directories(base_path)
    path = runtime_dir / name
    if not path.exists():
        path = latest_archive_files(runtime_dir).get(name)
    if not path or not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get_runtime_state() -> dict:
    elapsed = None
    if runtime_state["started_at"]:
        elapsed = int(time.time() - runtime_state["started_at"])
    return {
        "running": runtime_state["running"],
        "thread_count": runtime_state["thread_count"],
        "started_at": runtime_state["started_at"],
        "elapsed_seconds": elapsed,
        "last_error": runtime_state["last_error"],
        "success_count": runtime_state["success_count"],
        "site_key": config.get("site_key"),
        "action_id": config.get("action_id"),
        "browser_trace": runtime_state.get("browser_trace", {}),
    }


def read_accounts_file(base_path: str | Path = "keys") -> list[str]:
    return _read_result_file("accounts.txt", base_path)


def read_sso_file(base_path: str | Path = "keys") -> list[str]:
    return _read_result_file("grok.txt", base_path)

def parse_thread_count(raw_value: str, default: int = 8) -> int:
    try:
        value = int((raw_value or "").strip() or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def initialize_runtime(thread_count: int = 8):
    global PROXIES
    ensure_runtime_directories()
    PROXIES = resolve_proxies(PROXIES)
    html = preflight_site_access(proxies=PROXIES)
    soup = BeautifulSoup(html, "html.parser")

    key_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', html)
    if key_match:
        config["site_key"] = key_match.group(1)

    tree_match = re.search(r'next-router-state-tree":"([^"]+)"', html)
    if tree_match:
        config["state_tree"] = tree_match.group(1)

    discovered_action_ids = []
    js_urls = [
        urljoin(site_url, script["src"])
        for script in soup.find_all("script", src=True)
        if "_next/static" in script["src"]
    ]
    for js_url in js_urls:
        try:
            js_content = requests.get(
                js_url,
                proxies=PROXIES,
                impersonate="chrome120",
                timeout=20,
            ).text
        except Exception:
            continue
        for action_id in re.findall(r"7f[a-fA-F0-9]{40}", js_content):
            if action_id not in discovered_action_ids:
                discovered_action_ids.append(action_id)

    if not discovered_action_ids:
        raise RuntimeError("Could not extract Action ID from Next.js chunks")

    config["action_id"] = discovered_action_ids[0]
    config["action_ids"] = discovered_action_ids
    runtime_state["thread_count"] = thread_count
    return get_runtime_state()


def start_registration(thread_count: int = 8):
    global start_time
    thread_count = parse_thread_count(str(thread_count), default=8)
    if runtime_state["running"]:
        return get_runtime_state()
    initialize_runtime(thread_count)
    stop_event.clear()
    start_time = time.time()
    runtime_state["running"] = True
    runtime_state["thread_count"] = thread_count
    runtime_state["started_at"] = start_time
    runtime_state["last_error"] = None
    runtime_state["success_count"] = success_count
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=thread_count)
    for _ in range(thread_count):
        executor.submit(register_single_thread)
    return get_runtime_state()


def stop_registration():
    runtime_state["running"] = False
    stop_event.set()
    return get_runtime_state()


def _normalize_proxy_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "://" not in value:
        return f"http://{value}"
    return value


def parse_proxy_server(proxy_server: str):
    proxy_server = (proxy_server or "").strip()
    if not proxy_server:
        return {}

    proxies = {}
    if "=" not in proxy_server:
        normalized = _normalize_proxy_url(proxy_server)
        return {"http": normalized, "https": normalized}

    for item in proxy_server.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        scheme, value = item.split("=", 1)
        scheme = scheme.strip().lower()
        normalized = _normalize_proxy_url(value)
        if scheme in {"http", "https"} and normalized:
            proxies[scheme] = normalized

    if "http" in proxies and "https" not in proxies:
        proxies["https"] = proxies["http"]
    if "https" in proxies and "http" not in proxies:
        proxies["http"] = proxies["https"]
    return proxies


def get_windows_proxy_server():
    if os.name != "nt":
        return ""

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            proxy_enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            if not proxy_enabled:
                return ""
            return str(winreg.QueryValueEx(key, "ProxyServer")[0] or "").strip()
    except Exception:
        return ""


def resolve_proxies(default_proxies=None):
    env_http = _normalize_proxy_url(os.getenv("HTTP_PROXY", ""))
    env_https = _normalize_proxy_url(os.getenv("HTTPS_PROXY", ""))
    if env_http or env_https:
        return {
            "http": env_http or env_https,
            "https": env_https or env_http,
        }

    windows_proxy = parse_proxy_server(get_windows_proxy_server())
    if windows_proxy:
        return windows_proxy

    return dict(default_proxies or {})


def preflight_site_access(requests_module=requests, proxies=None, timeout=30):
    response = requests_module.get(
        f"{site_url}/sign-up",
        proxies=proxies,
        impersonate="chrome120",
        timeout=timeout,
    )
    return response.text


def _reason_from_account_response(response) -> str:
    url = str(getattr(response, "url", "") or "")
    text = str(getattr(response, "text", "") or "")
    lowered_url = url.lower()
    lowered_text = text.lower()
    if "/accept-tos" in lowered_url or "accept terms of service" in lowered_text:
        return "accept_tos_required"
    if "/log-in" in lowered_url or "/sign-up" in lowered_url:
        return "not_authenticated"
    return "ok"


def is_account_usable(sso: str) -> tuple[bool, str]:
    if not sso:
        return False, "missing_sso"
    try:
        with requests.Session(impersonate="chrome120", proxies=PROXIES) as session:
            session.cookies.set("sso", sso, domain=".x.ai")
            response = session.get(f"{site_url}/", timeout=20, allow_redirects=True)
    except Exception as exc:
        return False, f"request_error:{exc}"
    reason = _reason_from_account_response(response)
    return reason == "ok", reason


def extract_tos_acceptance_details_from_page(html: str) -> dict:
    script_urls = [
        urljoin(site_url, src)
        for src in re.findall(r'<script[^>]+src="([^"]+)"', html or "", re.I)
        if "/_next/static/chunks/" in src
    ]
    tos_version = 1
    matched_script = None

    try:
        with requests.Session(impersonate="chrome120", proxies=PROXIES) as session:
            for script_url in script_urls:
                try:
                    js = session.get(script_url, timeout=20).text
                except Exception:
                    continue
                if "setTosAcceptedVersion" not in js:
                    continue
                matched_script = script_url
                version_match = re.search(r'TOS_ACCEPTED_VERSION"\s*,\s*0\s*,\s*(\d+)', js)
                if version_match:
                    tos_version = int(version_match.group(1))
                break
    except Exception:
        pass

    return {
        "tos_version": tos_version,
        "script_url": matched_script,
    }


def encode_set_tos_accepted_version_request(tos_version: int) -> bytes:
    payload = struct.pack("B", (2 << 3) | 0) + struct.pack("B", tos_version)
    return b"\x00" + struct.pack(">I", len(payload)) + payload


def run_async(coro):
    return asyncio.run(coro)


def _record_browser_trace(**kwargs):
    trace = dict(runtime_state.get("browser_trace") or {})
    trace.update(kwargs)
    trace["updated_at"] = int(time.time())
    runtime_state["browser_trace"] = trace
    return trace


def _extract_sso_from_storage_state(storage_state: dict) -> str:
    if not isinstance(storage_state, dict):
        return ""
    for cookie in storage_state.get("cookies") or []:
        if cookie.get("name") == "sso" and cookie.get("value"):
            return cookie["value"]

    for origin_state in storage_state.get("origins") or []:
        for entry in origin_state.get("localStorage") or []:
            if entry.get("name") == "sso" and entry.get("value"):
                return entry["value"]
        for entry in origin_state.get("sessionStorage") or []:
            if entry.get("name") == "sso" and entry.get("value"):
                return entry["value"]

    return ""


def _extract_sso_from_browser_cookies(cookies) -> str:
    for cookie in cookies or []:
        if cookie.get("name") == "sso" and cookie.get("value"):
            return cookie["value"]
    return ""


async def _extract_signup_sso_from_browser_context(context, page, bootstrap_url: str = "") -> tuple[str, str]:
    try:
        cookies = await context.cookies()
    except Exception:
        cookies = []
    sso = _extract_sso_from_browser_cookies(cookies)
    if sso:
        return sso, "ok"

    try:
        current_url = page.url or ""
    except Exception:
        current_url = ""
    if not bootstrap_url and current_url and "set-cookie?q=" in current_url:
        bootstrap_url = current_url

    if not bootstrap_url:
        try:
            page_content = await page.content()
        except Exception:
            page_content = ""
        match = re.search(r'(https://[^"\s]+set-cookie\?q=[^:"\s]+)1:', page_content)
        if match:
            bootstrap_url = match.group(1)

    if bootstrap_url:
        try:
            await page.goto(bootstrap_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        try:
            cookies = await context.cookies()
        except Exception:
            cookies = []
        sso = _extract_sso_from_browser_cookies(cookies)
        if sso:
            return sso, "ok"

    try:
        storage_state = await context.storage_state()
    except Exception:
        storage_state = {}
    sso = _extract_sso_from_storage_state(storage_state)
    if sso:
        return sso, "ok"

    try:
        current_url = page.url
    except Exception:
        current_url = ""
    if current_url and "/accept-tos" in current_url:
        return "", "accept_tos_required"
    return "", "browser_signup_sso_not_found"


def _extract_bootstrap_url_from_response_text(response_text: str) -> str:
    if not response_text:
        return ""
    match = re.search(r'https://[^"\s]+set-cookie\?q=[^:"\s]+', response_text)
    if match:
        return match.group(0)
    return ""


async def _signup_route_handler(route):
    url = route.request.url
    resource_type = route.request.resource_type
    allowed_types = {"document", "script", "xhr", "fetch", "stylesheet", "image", "font"}
    allowed_domains = [
        "accounts.x.ai",
        "x.ai",
        "challenges.cloudflare.com",
        "static.cloudflareinsights.com",
        "cloudflare.com",
    ]
    if resource_type in allowed_types or any(domain in url for domain in allowed_domains):
        await route.continue_()
    else:
        await route.abort()


async def _enable_signup_page_optimizations(page):
    await page.route("**/*", _signup_route_handler)
    await page.add_init_script(
        """
        (function() {
          const originalAttachShadow = Element.prototype.attachShadow;
          Element.prototype.attachShadow = function(init) {
            const shadow = originalAttachShadow.call(this, init);
            if (init && init.mode === 'closed') {
              window.__lastClosedShadowRoot = shadow;
            }
            return shadow;
          };
        })();
        """
    )


async def _disable_signup_page_optimizations(page):
    try:
        await page.unroute("**/*", _signup_route_handler)
    except Exception:
        pass


async def _inject_turnstile_token(page, token: str):
    await page.evaluate(
        """
        ({ token }) => {
            let input = document.querySelector('input[name="cf-turnstile-response"]');
            if (!input) {
                input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'cf-turnstile-response';
                document.body.appendChild(input);
            }
            input.value = token;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            if (typeof window.onTurnstileCallback === 'function') {
                try { window.onTurnstileCallback(token); } catch (e) {}
            }
            document.querySelectorAll('[data-callback]').forEach((el) => {
                const callbackName = el.getAttribute('data-callback');
                if (callbackName && typeof window[callbackName] === 'function') {
                    try { window[callbackName](token); } catch (e) {}
                }
            });
        }
        """,
        {"token": token},
    )


async def _create_signup_browser_context(playwright):
    launch_kwargs = {
        "headless": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            f"--user-agent={user_agent}",
        ],
    }
    browser = await playwright.chromium.launch(**launch_kwargs)
    context_kwargs = {
        "user_agent": user_agent,
        "viewport": {"width": 1440, "height": 960},
        "locale": "en-US",
        "timezone_id": "UTC",
        "color_scheme": "light",
        "ignore_https_errors": True,
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
        },
    }
    browser_proxy = PROXIES.get("https") or PROXIES.get("http") or ""
    if browser_proxy:
        context_kwargs["proxy"] = {"server": browser_proxy}
        _record_browser_trace(browser_proxy=browser_proxy)
    context = await browser.new_context(**context_kwargs)
    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        window.chrome = window.chrome || { runtime: {} };
        """
    )
    return browser, context


def _is_cloudflare_block_page(page_content: str, page_title: str = "", page_url: str = "") -> bool:
    combined = " ".join(part.lower() for part in [page_content or "", page_title or "", page_url or ""])
    return (
        "attention required! | cloudflare" in combined
        or "sorry, you have been blocked" in combined
        or "cf-error-details" in combined
    )


async def _prepare_signup_page(page, token: str) -> tuple[bool, str]:
    await _enable_signup_page_optimizations(page)
    response_log = []

    def _capture_response(response):
        try:
            response_log.append({
                "url": response.url,
                "status": response.status,
                "method": response.request.method,
            })
        except Exception:
            pass

    page.on("response", _capture_response)
    await page.goto(f"{site_url}/sign-up", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)

    async def _trace_challenge_state(phase_name: str, html_snapshot: str, title_text: str, current_url: str):
        try:
            email_visible = await page.locator('input[type="email"]').count() > 0
        except Exception:
            email_visible = False
        iframe_selectors = [
            'iframe[src*="challenges.cloudflare.com"]',
            'iframe[src*="turnstile"]',
            'iframe[title*="widget"]',
        ]
        iframe_counts = {}
        for selector in iframe_selectors:
            try:
                iframe_counts[selector] = await page.locator(selector).count()
            except Exception:
                iframe_counts[selector] = 0
        try:
            cookies = await page.context.cookies()
        except Exception:
            cookies = []
        cookie_names = sorted({cookie.get("name", "") for cookie in cookies if cookie.get("name")})
        has_cf_clearance = any(cookie.get("name") == "cf_clearance" for cookie in cookies)
        _record_browser_trace(
            phase=phase_name,
            page_title=title_text[:200],
            page_url=current_url,
            email_visible=email_visible,
            blocked=_is_cloudflare_block_page(html_snapshot, title_text, current_url),
            responses=response_log[-10:],
            iframe_counts=iframe_counts,
            cookie_names=cookie_names,
            has_cf_clearance=has_cf_clearance,
        )
        return email_visible, has_cf_clearance

    try:
        title = await page.title()
    except Exception:
        title = ""
    try:
        content = await page.content()
    except Exception:
        content = ""
    current_url = getattr(page, "url", "")

    await _trace_challenge_state("initial_signup_page", content, title, current_url)

    if _is_cloudflare_block_page(content, title, current_url):
        sitekey_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', content)
        block_sitekey = sitekey_match.group(1) if sitekey_match else config.get("site_key")
        _record_browser_trace(block_sitekey=block_sitekey or "", token_present=bool(token))
        if token and block_sitekey:
            await _inject_turnstile_token(page, token)
            await page.wait_for_timeout(1500)
            try:
                content = await page.content()
            except Exception:
                content = ""
            try:
                title = await page.title()
            except Exception:
                title = title
            current_url = getattr(page, "url", "")
            email_visible, has_cf_clearance = await _trace_challenge_state(
                "after_turnstile_injection", content, title, current_url
            )
            if has_cf_clearance and _is_cloudflare_block_page(content, title, current_url) and not email_visible:
                await page.goto(f"{site_url}/sign-up", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)
                try:
                    content = await page.content()
                except Exception:
                    content = ""
                try:
                    title = await page.title()
                except Exception:
                    title = title
                current_url = getattr(page, "url", "")
                email_visible, has_cf_clearance = await _trace_challenge_state(
                    "after_clearance_renavigate", content, title, current_url
                )
            if _is_cloudflare_block_page(content, title, current_url) and not has_cf_clearance and not email_visible:
                return False, "cloudflare_blocked"
        else:
            return False, "cloudflare_blocked"

    await _disable_signup_page_optimizations(page)
    return True, "ok"


async def complete_signup_in_browser_context(email: str, password: str, verify_code: str, token: str) -> tuple[bool, str, str]:
    playwright = await async_playwright().start()
    browser, context = await _create_signup_browser_context(playwright)
    try:
        page = await context.new_page()
        page_ready, page_reason = await _prepare_signup_page(page, token)
        if not page_ready:
            return False, page_reason, ""

        consent_selectors = [
            'button:has-text("Reject All")',
            'button:has-text("Confirm My Choices")',
            'button:has-text("Allow All")',
        ]
        for selector in consent_selectors:
            try:
                await page.click(selector, timeout=2000)
                break
            except Exception:
                continue

        action_selectors = [
            'button:has-text("Sign up with email")',
            'a:has-text("Sign up with email")',
            '[role="button"]:has-text("Sign up with email")',
            'text="Sign up with email"',
        ]
        for selector in action_selectors:
            try:
                await page.click(selector, timeout=3000)
                await page.wait_for_timeout(1000)
                _record_browser_trace(phase="after_signup_entry_click", entry_selector=selector, page_url=getattr(page, "url", ""))
                break
            except Exception:
                continue
        else:
            return False, "browser_signup_entry_not_found", ""

        email_selectors = [
            'input[type="email"]',
            'input[name*="email" i]',
            'input[autocomplete="email"]',
        ]
        email_filled = False
        for selector in email_selectors:
            try:
                await page.fill(selector, email, timeout=3000)
                email_filled = True
                break
            except Exception:
                continue
        if not email_filled:
            return False, "browser_signup_email_not_found", ""

        password_selectors = [
            'input[type="password"]',
            'input[name*="password" i]',
            'input[autocomplete="new-password"]',
        ]
        password_filled = False
        for selector in password_selectors:
            try:
                await page.fill(selector, password, timeout=3000)
                password_filled = True
                break
            except Exception:
                continue
        if not password_filled:
            return False, "browser_signup_password_not_found", ""

        verify_selectors = [
            'input[name*="code" i]',
            'input[autocomplete="one-time-code"]',
            'input[inputmode="numeric"]',
            'input[type="text"]',
        ]
        for selector in verify_selectors:
            try:
                await page.fill(selector, verify_code, timeout=2000)
                break
            except Exception:
                continue

        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Create")',
            'button:has-text("Sign up")',
        ]
        submitted = False
        bootstrap_url = ""
        for selector in submit_selectors:
            try:
                async with page.expect_response(lambda response: response.request.method == "POST", timeout=5000) as response_info:
                    await page.click(selector, timeout=3000)
                response = await response_info.value
                bootstrap_url = _extract_bootstrap_url_from_response_text(getattr(response, "text", lambda: "")())
                submitted = True
                break
            except Exception:
                try:
                    await page.click(selector, timeout=3000)
                    submitted = True
                    break
                except Exception:
                    continue
        if not submitted:
            return False, "browser_signup_submit_not_found", ""

        await page.wait_for_timeout(5000)
        try:
            email_visible = await page.locator('input[type="email"]').count() > 0
        except Exception:
            email_visible = False
        try:
            page_title = await page.title()
        except Exception:
            page_title = ""
        _record_browser_trace(
            phase="after_signup_submit",
            page_title=page_title[:200],
            page_url=getattr(page, "url", ""),
            email_visible=email_visible,
            bootstrap_url=bootstrap_url,
        )

        sso, reason = await _extract_signup_sso_from_browser_context(context, page, bootstrap_url=bootstrap_url)
        if sso:
            return True, "ok", sso
        return False, reason, ""
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()


def _persist_success_account(email: str, password: str, sso: str):
    global success_count
    with file_lock:
        ensure_runtime_directories()
        with open("keys/grok.txt", "a", encoding="utf-8") as f:
            f.write(sso + "\n")
        with open("keys/accounts.txt", "a", encoding="utf-8") as f:
            f.write(f"{email}:{password}:{sso}\n")
        success_count += 1
        runtime_state["success_count"] = success_count
        avg = (time.time() - start_time) / success_count
        return avg


async def complete_tos_in_browser_context(sso: str) -> tuple[bool, str]:
    if not sso:
        return False, "missing_sso"
    playwright = await async_playwright().start()
    browser, context = await _create_signup_browser_context(playwright)
    try:
        await context.add_cookies([
            {
                "name": "sso",
                "value": sso,
                "domain": ".x.ai",
                "path": "/",
                "httpOnly": False,
                "secure": False,
            }
        ])
        page = await context.new_page()
        await page.goto(f"{site_url}/accept-tos", wait_until="domcontentloaded", timeout=30000)
        clicked = False
        selectors = [
            'label:has(input[name="readTerms"]) button[role="checkbox"]',
            'input[name="readTerms"]',
            'label:has(input[name="ageLimit"]) button[role="checkbox"]',
            'input[name="ageLimit"]',
            'button[role="checkbox"]',
        ]
        for selector in selectors:
            try:
                await page.click(selector, timeout=3000)
                clicked = True
            except Exception:
                continue
        if not clicked:
            clicked = bool(await page.evaluate("""
                (() => {
                  const readTerms = document.querySelector('input[name="readTerms"]');
                  const ageLimit = document.querySelector('input[name="ageLimit"]');
                  if (readTerms) {
                    readTerms.checked = true;
                    readTerms.dispatchEvent(new Event('click', { bubbles: true }));
                    readTerms.dispatchEvent(new Event('change', { bubbles: true }));
                  }
                  if (ageLimit) {
                    ageLimit.checked = true;
                    ageLimit.dispatchEvent(new Event('click', { bubbles: true }));
                    ageLimit.dispatchEvent(new Event('change', { bubbles: true }));
                  }
                  const submit = document.querySelector('button[type="submit"]');
                  if (submit) {
                    submit.click();
                    return true;
                  }
                  return false;
                })()
            """))
        if clicked:
            try:
                await page.click('button[type="submit"]', timeout=5000)
            except Exception:
                pass
        await page.wait_for_timeout(3000)
        current_url = getattr(page, "url", "")
        if "/accept-tos" in current_url:
            return False, "accept_tos_required"
        return True, "ok"
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()


def generate_random_name() -> str:
    length = random.randint(4, 6)
    return random.choice(string.ascii_uppercase) + "".join(
        random.choice(string.ascii_lowercase) for _ in range(length - 1)
    )


def generate_random_string(length: int = 15) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def encode_grpc_message(field_id, string_value):
    key = (field_id << 3) | 2
    value_bytes = string_value.encode("utf-8")
    length = len(value_bytes)
    payload = struct.pack("B", key) + struct.pack("B", length) + value_bytes
    return b"\x00" + struct.pack(">I", len(payload)) + payload


def encode_grpc_message_verify(email, code):
    p1 = struct.pack("B", (1 << 3) | 2) + struct.pack("B", len(email)) + email.encode("utf-8")
    p2 = struct.pack("B", (2 << 3) | 2) + struct.pack("B", len(code)) + code.encode("utf-8")
    payload = p1 + p2
    return b"\x00" + struct.pack(">I", len(payload)) + payload


def send_email_code_grpc(session, email):
    url = f"{site_url}/auth_mgmt.AuthManagement/CreateEmailValidationCode"
    data = encode_grpc_message(1, email)
    headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        "origin": site_url,
        "referer": f"{site_url}/sign-up?redirect=grok-com",
    }
    try:
        res = session.post(url, data=data, headers=headers, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"[-] {email} Failed to send verification code: {e}")
        return False


def verify_email_code_grpc(session, email, code):
    url = f"{site_url}/auth_mgmt.AuthManagement/VerifyEmailValidationCode"
    data = encode_grpc_message_verify(email, code)
    headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        "origin": site_url,
        "referer": f"{site_url}/sign-up?redirect=grok-com",
    }
    try:
        print(f"[debug] {email} Verifying code: {code}")
        res = session.post(url, data=data, headers=headers, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"[-] {email} Failed to verify email code: {e}")
        return False


def register_single_thread():
    # Stagger worker startup to avoid a burst of requests.
    time.sleep(random.uniform(0, 5))

    try:
        email_service = EmailService(proxies=PROXIES)
        turnstile_service = TurnstileService()
    except Exception as e:
        print(f"[-] Failed to initialize services: {e}")
        runtime_state["last_error"] = str(e)
        return

    final_action_id = config["action_id"]
    if not final_action_id:
        print("[-] Worker exiting: missing Action ID")
        runtime_state["last_error"] = "missing Action ID"
        return

    while not stop_event.is_set():
        try:
            with requests.Session(impersonate="chrome120", proxies=PROXIES) as session:
                try:
                    session.get(site_url, timeout=10)
                except Exception:
                    pass

                password = generate_random_string()

                try:
                    jwt, email = email_service.create_email()
                except Exception as e:
                    print(f"[-] Email service raised an exception: {e}")
                    jwt, email = None, None

                if not email:
                    print(
                        f"[-] Worker-{threading.get_ident()} did not receive an email address. "
                        "The provider may be down or timing out. Waiting 5s..."
                    )
                    time.sleep(5)
                    continue

                print(f"[*] Starting registration: {email}")

                if not send_email_code_grpc(session, email):
                    print(f"[-] {email} Failed to send verification code")
                    time.sleep(5)
                    continue

                verify_code = None
                for _ in range(30):
                    if stop_event.is_set():
                        return
                    time.sleep(1)
                    content = email_service.fetch_first_email(jwt)
                    if content:
                        match = re.search(r">([A-Z0-9]{3}-[A-Z0-9]{3})<", content)
                        if match:
                            verify_code = match.group(1).replace("-", "")
                            break

                if not verify_code:
                    print(f"[-] {email} Verification code was not received")
                    continue

                if not verify_email_code_grpc(session, email, verify_code):
                    print(f"[-] {email} Verification code is invalid")
                    continue

                for attempt in range(3):
                    if stop_event.is_set():
                        return
                    task_id = turnstile_service.create_task(site_url, config["site_key"])
                    token = turnstile_service.get_response(task_id, max_retries=90, initial_delay=5, retry_delay=2)

                    if not token or token == "CAPTCHA_FAIL":
                        print(f"[-] {email} CAPTCHA failed, retrying...")
                        continue

                    action_candidates = list(config.get("action_ids") or [])
                    if not action_candidates and config.get("action_id"):
                        action_candidates = [config["action_id"]]

                    signup_succeeded = False
                    for action_index, final_action_id in enumerate(action_candidates, start=1):
                        headers = {
                            "user-agent": user_agent,
                            "accept": "text/x-component",
                            "content-type": "text/plain;charset=UTF-8",
                            "origin": site_url,
                            "referer": f"{site_url}/sign-up",
                            "cookie": f"__cf_bm={session.cookies.get('__cf_bm', '', domain='.x.ai')}",
                            "next-router-state-tree": config["state_tree"],
                            "next-action": final_action_id,
                        }
                        payload = [
                            {
                                "emailValidationCode": verify_code,
                                "createUserAndSessionRequest": {
                                    "email": email,
                                    "givenName": generate_random_name(),
                                    "familyName": generate_random_name(),
                                    "clearTextPassword": password,
                                    "tosAcceptedVersion": "$undefined",
                                },
                                "turnstileToken": token,
                                "promptOnDuplicateEmail": True,
                            }
                        ]

                        with post_lock:
                            print(
                                f"[debug] {email} Submitting sign-up with action={final_action_id} "
                                f"candidate={action_index}/{len(action_candidates)} "
                                f"token_prefix={token[:24] if token else 'NONE'} token_len={len(token) if token else 0}"
                            )
                            res = session.post(f"{site_url}/sign-up", json=payload, headers=headers)

                        snippet = res.text[:500].replace("\n", " ")
                        print(f"[debug] {email} Submission response status={res.status_code} snippet={snippet}")

                        if res.status_code == 404 and "Server action not found" in res.text:
                            continue

                        if res.status_code == 200:
                            match = re.search(r'(https://[^" \s]+set-cookie\?q=[^:" \s]+)1:', res.text)
                            if match:
                                verify_url = match.group(1)
                                session.get(verify_url, allow_redirects=True)
                                sso = session.cookies.get("sso")
                                if sso:
                                    usable, reason = is_account_usable(sso)
                                    if not usable and reason == "accept_tos_required":
                                        tos_completed, tos_reason = run_async(complete_tos_in_browser_context(sso))
                                        if tos_completed:
                                            usable, reason = is_account_usable(sso)
                                        else:
                                            reason = tos_reason
                                    if not usable:
                                        print(f"[-] {email} Session rejected after signup: {reason}")
                                        time.sleep(2)
                                        signup_succeeded = True
                                        break
                                    avg = _persist_success_account(email, password, sso)
                                    print(f"[+] Registration succeeded: {email} | SSO: {sso[:15]}... | Avg: {avg:.1f}s")
                                    signup_succeeded = True
                                    break
                            browser_ok, browser_reason, browser_sso = run_async(
                                complete_signup_in_browser_context(email, password, verify_code, token)
                            )
                            if browser_ok and browser_sso:
                                usable, reason = is_account_usable(browser_sso)
                                if not usable and reason == "accept_tos_required":
                                    tos_completed, tos_reason = run_async(complete_tos_in_browser_context(browser_sso))
                                    if tos_completed:
                                        usable, reason = is_account_usable(browser_sso)
                                    else:
                                        reason = tos_reason
                                if usable:
                                    avg = _persist_success_account(email, password, browser_sso)
                                    print(f"[+] Registration succeeded via browser fallback: {email} | SSO: {browser_sso[:15]}... | Avg: {avg:.1f}s")
                                    signup_succeeded = True
                                    break
                                print(f"[-] {email} Browser fallback session rejected: {reason}")
                                time.sleep(2)
                                signup_succeeded = True
                                break
                            print(f"[-] {email} Submission returned 200 without session bootstrap ({browser_reason})")
                            time.sleep(3)
                            signup_succeeded = True
                            break

                        print(f"[-] {email} Submission failed ({res.status_code})")
                        time.sleep(3)
                        signup_succeeded = True
                        break

                    if signup_succeeded:
                        break
                else:
                    print(f"[-] {email} Giving up and rotating to a new account")
                    time.sleep(5)

        except Exception as e:
            runtime_state["last_error"] = str(e)
            print(f"[-] Worker exception: {str(e)[:50]}")
            time.sleep(5)


def main():
    global PROXIES
    ensure_runtime_directories()
    print("=" * 60 + "\nGrok Register\n" + "=" * 60)

    PROXIES = resolve_proxies(PROXIES)
    if PROXIES:
        print(f"[*] Using proxy: {PROXIES.get('https') or PROXIES.get('http')}")
    else:
        print("[*] No proxy configured")

    try:
        state = initialize_runtime()
    except Exception as e:
        print(f"[-] Initialization failed: {e}")
        return

    print(f"[+] Action ID: {state['action_id']}")

    try:
        t = int(input("\nThread count (default 8): ").strip() or 8)
    except Exception:
        t = 8
    t = parse_thread_count(str(t), default=8)

    print(f"[*] Starting {t} worker threads...")
    start_registration(t)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Received stop signal, shutting down workers...")
        stop_registration()


if __name__ == "__main__":
    main()
