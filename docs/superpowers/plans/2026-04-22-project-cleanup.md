# Project Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project easier to install and run without changing the registration or solver behavior.

**Architecture:** Keep the existing script-first structure. Add a small amount of testable startup logic in `grok.py`, document dependencies explicitly, and replace the unreadable README with a clean UTF-8 version.

**Tech Stack:** Python 3.10+, pytest, curl_cffi, requests, quart, playwright, camoufox, patchright, python-dotenv, beautifulsoup4, rich

---

### Task 1: Add dependency manifest

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Write the dependency manifest**

```text
beautifulsoup4
camoufox
curl_cffi
patchright
playwright
python-dotenv
quart
requests
rich
```

- [ ] **Step 2: Verify the file content**

Run: `Get-Content requirements.txt`
Expected: the file lists the nine dependencies shown above

### Task 2: Add failing tests for startup helpers

**Files:**
- Create: `tests/test_grok_setup.py`
- Modify: `grok.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from grok import ensure_runtime_directories, parse_thread_count


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_grok_setup.py -v`
Expected: FAIL because `ensure_runtime_directories` and `parse_thread_count` do not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
from pathlib import Path


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_grok_setup.py -v`
Expected: PASS

### Task 3: Wire startup helpers into the main script

**Files:**
- Modify: `grok.py`

- [ ] **Step 1: Update startup flow to create runtime directories and use parsed input**

```python
def main():
    print("=" * 60 + "\nGrok Register\n" + "=" * 60)
    ensure_runtime_directories()
    # startup scan remains unchanged
    thread_count = parse_thread_count(input("\nThreads (default 8): "), default=8)
```

- [ ] **Step 2: Verify the script still parses**

Run: `py -3 -m py_compile grok.py g\\email_service.py g\\turnstile_service.py api_solver.py db_results.py browser_configs.py`
Expected: no output and exit code 0

### Task 4: Replace the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite the README in UTF-8**

```markdown
# grok-register

Automates the x.ai sign-up flow by creating temporary Mail.tm inboxes, requesting email verification codes, solving Cloudflare Turnstile, and storing successful account tokens locally.

## Files

- `grok.py`: main registration runner
- `g/`: Mail.tm and Turnstile service wrappers
- `api_solver.py`: optional local Turnstile solver API
- `requirements.txt`: Python dependencies
- `keys/`: generated output files at runtime

## Setup

1. Create and activate a Python 3.10+ virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. If using the local browser solver, install Chromium with `python -m playwright install chromium`.
4. Copy `.env.example` to `.env` and set `YESCAPTCHA_KEY` if using YesCaptcha.

## Running

### Default mode

Run `python grok.py` and enter the desired thread count when prompted.

### Local solver mode

Start `python api_solver.py --browser_type chromium --thread 2 --debug` in one terminal, then run `python grok.py` in another.

## Output

- `keys/grok.txt`: one SSO token per line
- `keys/accounts.txt`: `email:password:sso` records
```

- [ ] **Step 2: Verify the README is readable**

Run: `Get-Content README.md`
Expected: clear UTF-8 text without mojibake

### Task 5: Verify the cleanup result

**Files:**
- Verify: `requirements.txt`
- Verify: `README.md`
- Verify: `grok.py`
- Verify: `tests/test_grok_setup.py`

- [ ] **Step 1: Run focused tests**

Run: `py -3 -m pytest tests/test_grok_setup.py -v`
Expected: all tests pass

- [ ] **Step 2: Run compile verification**

Run: `py -3 -m py_compile grok.py g\\email_service.py g\\turnstile_service.py api_solver.py db_results.py browser_configs.py`
Expected: no output and exit code 0

- [ ] **Step 3: Review file status**

Run: `Get-ChildItem requirements.txt,README.md,grok.py,tests\\test_grok_setup.py`
Expected: all target files exist
