# Project Cleanup Design

**Scope**

This cleanup keeps the current registration flow and solver behavior intact. The work is limited to maintainability and operability improvements: dependency documentation, startup safeguards, clearer runtime setup, and readable project documentation.

**Goals**

- Make the project installable from a single dependency manifest.
- Prevent first-run failures caused by missing runtime directories.
- Isolate small utility behavior so it can be tested without live network calls.
- Replace the current unreadable README with a clear setup and run guide.

**Non-Goals**

- No protocol changes to the x.ai registration flow.
- No refactor of the large solver implementation in `api_solver.py`.
- No persistence redesign for `db_results.py`.
- No GitHub or release automation.

**Approach Options**

1. Minimal hardening without code structure changes.
This would add `requirements.txt`, rewrite docs, and create `keys/` at startup. It is the smallest change set and best matches the requested scope.

2. Moderate cleanup with helper extraction.
This would also split some `grok.py` startup behavior into small testable helpers. It improves testability with low risk and is the recommended option.

3. Full maintainability pass.
This would include module decomposition, solver cleanup, and persistence changes. It would be materially larger and exceeds the requested scope.

**Chosen Approach**

Use option 2. Add the missing dependency manifest and documentation, then extract a few startup helpers in `grok.py` so the new behavior can be covered by unit tests.

**Design**

- Add `requirements.txt` with the libraries already referenced in the code and README.
- Add `tests/test_grok_setup.py` for the new helper functions.
- In `grok.py`, introduce focused helpers for:
  - ensuring the `keys/` runtime directory exists
  - parsing the thread count input with a safe default
  - writing successful account output through a small wrapper
- Keep registration network behavior unchanged.
- Rewrite `README.md` in UTF-8 with a concise project overview, setup instructions, environment variables, optional local solver usage, and output file descriptions.

**Testing**

- Unit tests cover the new helper behavior in `grok.py`.
- A compile check verifies that the edited Python files still parse.

**Risks**

- Importing `grok.py` in tests pulls in third-party modules. Tests must avoid invoking network code and only exercise pure helpers.
- The repository is not currently a Git repository, so the design artifact cannot be committed in this workspace state.
