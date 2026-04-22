# Encoding Cleanup Design

**Scope**

This cleanup standardizes source text and documentation across the repository. It covers mojibake in comments, docstrings, log messages, README content, and user-facing HTML text. It does not change protocol logic, request payloads, control flow, or solver behavior.

**Goals**

- Remove garbled text from all tracked source files.
- Normalize source content to readable UTF-8 text.
- Keep runtime behavior stable apart from cleaner output text.
- Preserve existing interfaces and command-line usage.

**Non-Goals**

- No refactor of request/solver logic.
- No database or persistence redesign.
- No API contract changes.

**Approach Options**

1. Replace only obviously broken strings.
This is the smallest change, but it leaves mixed language and mixed style in place.

2. Replace all garbled text and normalize wording style.
This removes mojibake and leaves the project readable without broad code changes. This is the recommended option.

3. Rewrite modules more aggressively while cleaning text.
This would improve structure too, but it expands beyond the current request.

**Chosen Approach**

Use option 2. Rewrite smaller files completely where that is safer than patching broken lines, and patch only the text-bearing lines in `api_solver.py`.

**File Strategy**

- Rewrite small files with clean UTF-8 text:
  - `grok.py`
  - `db_results.py`
  - `g/email_service.py`
  - `g/turnstile_service.py`
  - `g/__init__.py`
- Patch `api_solver.py` only where mojibake appears in comments, docstrings, and welcome-page strings.
- Keep `README.md` as already-clean UTF-8 text unless additional wording fixes are needed.

**Verification**

- Run a non-ASCII residue scan focused on known mojibake patterns.
- Run unit tests already present in `tests/test_grok_setup.py`.
- Run `py_compile` over edited Python files.

**Risk Control**

- Do not rename functions, endpoints, classes, or CLI flags.
- Do not alter API response shapes.
- Keep logging semantics intact even if text changes.
