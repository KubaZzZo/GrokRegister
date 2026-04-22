# GrokRegister

A Python-based automation project for the x.ai sign-up flow. The repository combines temporary email provisioning, email verification handling, Cloudflare Turnstile solving, and local token persistence into a single workflow.

## Overview

This project is organized around two runtime paths:

- `grok.py` runs the main registration workflow.
- `api_solver.py` exposes a local Turnstile-solving service backed by a browser.

Together, they provide a local toolchain that can:

- create temporary inboxes through TempMail.lol
- request and verify email validation codes
- solve Cloudflare Turnstile through either YesCaptcha or a local browser solver
- submit the final sign-up request
- save successful output to local files under `keys/`

## Features

- Multi-threaded registration runner
- TempMail.lol inbox creation and polling
- gRPC-web email code request and verification flow
- Two Turnstile solving modes:
  - local solver service
  - YesCaptcha API
- Automatic proxy detection from environment or Windows proxy settings
- Separate PowerShell launch scripts for convenience
- Basic test coverage for setup and service wrappers

## Repository Structure

```text
.
|-- grok.py                     # Main registration runner
|-- api_solver.py               # Local Turnstile solver API service
|-- browser_configs.py          # Browser fingerprint/header helpers
|-- db_results.py               # In-memory task result store
|-- g/
|   |-- __init__.py
|   |-- email_service.py        # TempMail.lol integration
|   `-- turnstile_service.py    # YesCaptcha / local solver wrapper
|-- tests/
|   |-- test_email_service.py
|   |-- test_grok_setup.py
|   `-- test_start_script.py
|-- start_project.ps1           # PowerShell launcher
|-- start_project.bat           # Batch launcher
|-- requirements.txt
`-- .env.example
```

## Environment Requirements

- Python 3.10+
- Windows PowerShell for the included launch scripts
- Optional: Playwright Chromium for local solver mode
- Optional: YesCaptcha API key

## Installation

### 1. Create a virtual environment

```bash
python -m venv .venv
```

### 2. Activate it

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Chromium for local solver mode

Only required if you plan to run `api_solver.py` locally.

```bash
python -m playwright install chromium
```

## Configuration

Create a `.env` file from `.env.example`:

```bash
copy .env.example .env
```

Example variables:

```env
# YesCaptcha API key
YESCAPTCHA_KEY="your_key_here"

# TempMail.lol API key
TEMPMAIL_LOL_API_KEY="your_key_here"

# Optional proxy examples
# HTTP_PROXY="http://127.0.0.1:7892"
# HTTPS_PROXY="http://127.0.0.1:7892"
```

### Configuration Notes

- If `YESCAPTCHA_KEY` is set, `g/turnstile_service.py` uses YesCaptcha.
- If `YESCAPTCHA_KEY` is not set, the project expects a local solver at `http://127.0.0.1:5072`.
- `HTTP_PROXY` and `HTTPS_PROXY` take priority over Windows proxy settings.
- If neither environment variables nor Windows proxy settings are available, the built-in defaults in `grok.py` are used.

## Usage

## Mode 1: Main Runner Only

Run the registration runner directly:

```bash
python grok.py
```

It will:

1. initialize runtime directories
2. detect proxy settings
3. fetch the sign-up page
4. discover required dynamic values such as the action ID
5. ask for thread count
6. start worker threads

## Mode 2: Local Solver + Main Runner

Start the local Turnstile solver:

```bash
python api_solver.py --browser_type chromium --thread 2 --debug
```

Then start the main runner in another terminal:

```bash
python grok.py
```

## Mode 3: PowerShell Launcher

Use the provided launcher to start one or both components:

```powershell
.\start_project.ps1
```

Useful options:

```powershell
.\start_project.ps1 -Thread 2
.\start_project.ps1 -NoSolverDebug
.\start_project.ps1 -OnlySolver
.\start_project.ps1 -OnlyMain
```

Or use the batch wrapper:

```cmd
start_project.bat
```

## Runtime Flow

At a high level, the project works like this:

1. fetch the x.ai sign-up page
2. extract dynamic values such as:
   - Turnstile site key
   - router state tree
   - action ID from Next.js assets
3. create a temporary inbox
4. request an email validation code
5. poll the inbox until the code arrives
6. verify the email code
7. solve Turnstile
8. submit the sign-up payload
9. extract the resulting `sso` cookie and save output locally

## Output Files

The project writes successful results into the `keys/` directory:

- `keys/grok.txt`: one `sso` token per line
- `keys/accounts.txt`: `email:password:sso`

The directory is created automatically when needed.

## Testing

Run the test suite with:

```bash
pytest tests
```

Current tests cover:

- runtime directory creation
- thread count parsing
- proxy parsing
- preflight request setup
- TempMail service wrappers
- launcher script expectations

## Troubleshooting

### Action ID not found

If the script prints that the action ID could not be found, the target site likely changed its frontend assets or page structure.

### Verification email never arrives

Possible causes:

- TempMail provider issues
- API key problems
- upstream request throttling
- proxy instability

### Turnstile solving fails repeatedly

Check:

- whether `YESCAPTCHA_KEY` is valid
- whether the local solver is running
- whether Chromium is installed
- whether the browser can access the target site

### GitHub or network environments

If you are running this on a machine with strict outbound filtering, proxy settings and direct HTTPS transport can affect both solver behavior and external service connectivity.

## Development Notes

- `db_results.py` stores solver state in memory only.
- Restarting `api_solver.py` clears pending task results.
- The repository currently does not include packaging, a database backend, or a deployment profile.
- The current test suite is lightweight and focused on setup-level validation rather than full end-to-end execution.

## Security Notes

- Keep `.env` out of version control.
- Treat files under `keys/` as sensitive local output.
- Avoid exposing API keys, tokens, or local result files in screenshots, logs, or public bug reports.

## License

No license file is currently included in this repository. Add one if you plan to distribute or reuse the project publicly.
