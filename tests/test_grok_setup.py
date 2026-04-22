from pathlib import Path
import sys
import types


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
    sys.modules.setdefault("g", g_module)


_install_import_stubs()

from grok import ensure_runtime_directories, parse_thread_count, parse_proxy_server, preflight_site_access


def test_ensure_runtime_directories_creates_keys_dir(tmp_path: Path):
    keys_dir = tmp_path / "keys"

    ensure_runtime_directories(keys_dir)

    assert keys_dir.exists()
    assert keys_dir.is_dir()


def test_parse_thread_count_uses_default_for_blank_input():
    assert parse_thread_count("") == 8


def test_parse_thread_count_rejects_invalid_value():
    assert parse_thread_count("abc") == 8


def test_parse_thread_count_rejects_non_positive_value():
    assert parse_thread_count("0") == 8


def test_parse_thread_count_accepts_positive_integer():
    assert parse_thread_count("12") == 12


def test_parse_proxy_server_uses_same_proxy_for_http_and_https():
    proxies = parse_proxy_server("127.0.0.1:7892")

    assert proxies == {
        "http": "http://127.0.0.1:7892",
        "https": "http://127.0.0.1:7892",
    }


def test_parse_proxy_server_supports_protocol_specific_values():
    proxies = parse_proxy_server("http=127.0.0.1:7892;https=127.0.0.1:7893")

    assert proxies == {
        "http": "http://127.0.0.1:7892",
        "https": "http://127.0.0.1:7893",
    }


def test_preflight_site_access_passes_proxies_to_request_layer():
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "<html></html>"

    class FakeRequests:
        @staticmethod
        def get(url, proxies=None, impersonate=None, timeout=None):
            captured["url"] = url
            captured["proxies"] = proxies
            captured["impersonate"] = impersonate
            captured["timeout"] = timeout
            return FakeResponse()

    html = preflight_site_access(
        requests_module=FakeRequests,
        proxies={"http": "http://127.0.0.1:7892", "https": "http://127.0.0.1:7892"},
        timeout=12,
    )

    assert html == "<html></html>"
    assert captured["url"] == "https://accounts.x.ai/sign-up"
    assert captured["proxies"]["https"] == "http://127.0.0.1:7892"
    assert captured["impersonate"] == "chrome120"
    assert captured["timeout"] == 12
