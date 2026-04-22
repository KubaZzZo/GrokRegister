# Encoding Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove mojibake from the repository while preserving runtime behavior.

**Architecture:** Small modules will be rewritten in place with the same public behavior and cleaner UTF-8 text. `api_solver.py` will receive targeted text-only edits so the large solver implementation remains stable.

**Tech Stack:** Python 3.10+, pytest, PowerShell, ripgrep

---

### Task 1: Rewrite small modules with clean text

**Files:**
- Modify: `grok.py`
- Modify: `db_results.py`
- Modify: `g/email_service.py`
- Modify: `g/turnstile_service.py`
- Modify: `g/__init__.py`
- Test: `tests/test_grok_setup.py`

- [ ] **Step 1: Keep behavior fixed while replacing garbled comments, docstrings, and prints**

```python
# Example target pattern
print(f"[-] {email} Failed to send verification code: {e}")
```

- [ ] **Step 2: Run focused tests**

Run: `py -3 -m pytest tests/test_grok_setup.py -v --basetemp .pytest_tmp`
Expected: PASS

### Task 2: Patch `api_solver.py` text-only lines

**Files:**
- Modify: `api_solver.py`

- [ ] **Step 1: Replace garbled welcome strings and comments only**

```python
combined_text.append("\nChannel: ", style="bold white")
```

- [ ] **Step 2: Verify syntax**

Run: `py -3 -m py_compile api_solver.py`
Expected: no output and exit code 0

### Task 3: Residue scan and full verification

**Files:**
- Verify: `grok.py`
- Verify: `api_solver.py`
- Verify: `db_results.py`
- Verify: `g/email_service.py`
- Verify: `g/turnstile_service.py`
- Verify: `g/__init__.py`

- [ ] **Step 1: Scan for known mojibake markers**

Run: `rg -n "馃|袟|褍|蟹|鍒|鍚|楠|娉|缁" grok.py api_solver.py db_results.py g\email_service.py g\turnstile_service.py g\__init__.py`
Expected: no matches

- [ ] **Step 2: Run focused tests again**

Run: `py -3 -m pytest tests/test_grok_setup.py -v --basetemp .pytest_tmp`
Expected: PASS

- [ ] **Step 3: Run compile verification**

Run: `py -3 -m py_compile grok.py g\email_service.py g\turnstile_service.py api_solver.py db_results.py browser_configs.py`
Expected: no output and exit code 0
