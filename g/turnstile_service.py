"""Turnstile service wrapper."""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


class TurnstileService:
    """Create and poll Turnstile solve tasks."""

    def __init__(self, solver_url="http://127.0.0.1:5072"):
        self.yescaptcha_key = os.getenv("YESCAPTCHA_KEY", "").strip()
        self.solver_url = solver_url
        self.yescaptcha_api = "https://api.yescaptcha.com"

    def create_task(self, siteurl, sitekey):
        if self.yescaptcha_key:
            url = f"{self.yescaptcha_api}/createTask"
            payload = {
                "clientKey": self.yescaptcha_key,
                "task": {
                    "type": "TurnstileTaskProxyless",
                    "websiteURL": siteurl,
                    "websiteKey": sitekey,
                },
            }
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if data.get("errorId") != 0:
                raise Exception(f"YesCaptcha task creation failed: {data.get('errorDescription')}")
            return data["taskId"]

        url = f"{self.solver_url}/turnstile?url={siteurl}&sitekey={sitekey}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()["taskId"]

    def get_response(self, task_id, max_retries=30, initial_delay=5, retry_delay=2):
        time.sleep(initial_delay)

        for _ in range(max_retries):
            try:
                if self.yescaptcha_key:
                    url = f"{self.yescaptcha_api}/getTaskResult"
                    payload = {
                        "clientKey": self.yescaptcha_key,
                        "taskId": task_id,
                    }
                    response = requests.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()

                    if data.get("errorId") != 0:
                        print(f"YesCaptcha result request failed: {data.get('errorDescription')}")
                        return None

                    if data.get("status") == "ready":
                        token = data.get("solution", {}).get("token")
                        if token:
                            return token
                        print("YesCaptcha response did not include a token")
                        return None

                    if data.get("status") != "processing":
                        print(f"YesCaptcha returned unknown status: {data.get('status')}")
                    time.sleep(retry_delay)
                    continue

                url = f"{self.solver_url}/result?id={task_id}"
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                captcha = data.get("solution", {}).get("token")

                if captcha:
                    if captcha != "CAPTCHA_FAIL":
                        return captcha
                    return None

                time.sleep(retry_delay)
            except Exception as e:
                print(f"Failed to fetch Turnstile response: {e}")
                time.sleep(retry_delay)

        return None
