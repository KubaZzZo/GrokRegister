import concurrent.futures
import os
import random
import re
import string
import struct
import threading
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests

from g import EmailService, TurnstileService

# Base configuration
site_url = "https://accounts.x.ai"
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
PROXIES = {
    "http": "http://127.0.0.1:7892",
    "https": "http://127.0.0.1:7892",
}

# Values discovered dynamically from the signup page.
config = {
    "site_key": "0x4AAAAAAAhr9JGVDZbrZOo0",
    "action_id": None,
    "state_tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fsign-up%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
}

post_lock = threading.Lock()
file_lock = threading.Lock()
success_count = 0
start_time = time.time()


def ensure_runtime_directories(base_path: str | Path = "keys") -> Path:
    runtime_dir = Path(base_path)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def parse_thread_count(raw_value: str, default: int = 8) -> int:
    try:
        value = int((raw_value or "").strip() or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


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
        return

    final_action_id = config["action_id"]
    if not final_action_id:
        print("[-] Worker exiting: missing Action ID")
        return

    while True:
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
                    task_id = turnstile_service.create_task(site_url, config["site_key"])
                    token = turnstile_service.get_response(task_id)

                    if not token or token == "CAPTCHA_FAIL":
                        print(f"[-] {email} CAPTCHA failed, retrying...")
                        continue

                    headers = {
                        "user-agent": user_agent,
                        "accept": "text/x-component",
                        "content-type": "text/plain;charset=UTF-8",
                        "origin": site_url,
                        "referer": f"{site_url}/sign-up",
                        "cookie": f"__cf_bm={session.cookies.get('__cf_bm', '')}",
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
                        res = session.post(f"{site_url}/sign-up", json=payload, headers=headers)

                    if res.status_code == 200:
                        match = re.search(r'(https://[^" \s]+set-cookie\?q=[^:" \s]+)1:', res.text)
                        if match:
                            verify_url = match.group(1)
                            session.get(verify_url, allow_redirects=True)
                            sso = session.cookies.get("sso")
                            if sso:
                                with file_lock:
                                    with open("keys/grok.txt", "a") as f:
                                        f.write(sso + "\n")
                                    with open("keys/accounts.txt", "a") as f:
                                        f.write(f"{email}:{password}:{sso}\n")
                                    global success_count
                                    success_count += 1
                                    avg = (time.time() - start_time) / success_count
                                    print(f"[+] Registration succeeded: {email} | SSO: {sso[:15]}... | Avg: {avg:.1f}s")
                                break

                    print(f"[-] {email} Submission failed ({res.status_code})")
                    time.sleep(3)
                else:
                    print(f"[-] {email} Giving up and rotating to a new account")
                    time.sleep(5)

        except Exception as e:
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

    print("[*] Initializing...")
    start_url = f"{site_url}/sign-up"
    with requests.Session(impersonate="chrome120", proxies=PROXIES) as session:
        try:
            html = preflight_site_access(proxies=PROXIES)
            key_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', html)
            if key_match:
                config["site_key"] = key_match.group(1)

            tree_match = re.search(r'next-router-state-tree":"([^"]+)"', html)
            if tree_match:
                config["state_tree"] = tree_match.group(1)

            soup = BeautifulSoup(html, "html.parser")
            js_urls = [
                urljoin(start_url, script["src"])
                for script in soup.find_all("script", src=True)
                if "_next/static" in script["src"]
            ]
            for js_url in js_urls:
                js_content = session.get(js_url).text
                match = re.search(r"7f[a-fA-F0-9]{40}", js_content)
                if match:
                    config["action_id"] = match.group(0)
                    print(f"[+] Action ID: {config['action_id']}")
                    break
        except Exception as e:
            print(f"[-] Initial scan failed: {e}")
            return

    if not config["action_id"]:
        print("[-] Error: Action ID was not found")
        return

    try:
        t = int(input("\nThread count (default 8): ").strip() or 8)
    except Exception:
        t = 8
    t = parse_thread_count(str(t), default=8)

    print(f"[*] Starting {t} worker threads...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=t) as executor:
        futures = [executor.submit(register_single_thread) for _ in range(t)]
        concurrent.futures.wait(futures)


if __name__ == "__main__":
    main()
