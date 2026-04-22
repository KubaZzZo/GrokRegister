# grok-register

Automates the x.ai sign-up flow by creating temporary Mail.tm inboxes, requesting email verification codes, solving Cloudflare Turnstile, and storing successful account tokens locally.

## Project Layout

- `grok.py`: main registration runner
- `g/`: Mail.tm and Turnstile service wrappers
- `api_solver.py`: optional local Turnstile solver API
- `browser_configs.py`: browser header and user-agent helpers
- `db_results.py`: in-memory task result storage for the local solver
- `requirements.txt`: Python dependencies

## Requirements

- Python 3.10 or newer
- Optional: a YesCaptcha API key
- Optional: Playwright Chromium for local solver mode

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. If you plan to use the local browser solver, install Chromium:

```bash
python -m playwright install chromium
```

4. Copy `.env.example` to `.env` and set `YESCAPTCHA_KEY` if you want to use YesCaptcha.

## Configuration

### YesCaptcha

If `.env` contains `YESCAPTCHA_KEY`, `g/turnstile_service.py` will use the YesCaptcha API.

```env
YESCAPTCHA_KEY="your_key_here"
```

### Proxy

If you need a proxy for the registration runner, edit the `PROXIES` dictionary in `grok.py`.

## Usage

### Default Mode

Run the main script and enter the desired thread count when prompted:

```bash
python grok.py
```

The script will create the `keys/` directory automatically if it does not exist.

### Local Solver Mode

Start the local solver in one terminal:

```bash
python api_solver.py --browser_type chromium --thread 2 --debug
```

Then run the registration script in another terminal:

```bash
python grok.py
```

## Output Files

- `keys/grok.txt`: one SSO token per line
- `keys/accounts.txt`: `email:password:sso` records

## Notes

- `db_results.py` stores solver task state in memory only. Restarting the solver clears pending results.
- The project currently does not ship a production persistence layer or CLI packaging.
