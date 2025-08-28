# core/captcha.py
#
# A minimal implementation of 2Captcha API integration.  This module
# defines the CaptchaSolver class which can be used by the scraper to
# solve various types of captchas (e.g. reCAPTCHA v2, hCaptcha) when
# encountered on property listing websites.  See README for usage.

import os
import time
import requests


class CaptchaSolver:
    """Simple client for 2Captcha.  Only the API methods used by the
    scraper are implemented here.  To use this class you must set the
    environment variable ``RP_CAPTCHA_APIKEY`` to a valid 2Captcha API key.

    This class hides the details of submitting a captcha challenge to
    2Captcha and polling for the result.  If you need more fine‑grained
    control or wish to support additional captcha types, extend this
    implementation as needed.
    """

    API_KEY = os.getenv("RP_CAPTCHA_APIKEY")
    SUBMIT_URL = "https://2captcha.com/in.php"
    POLL_URL = "https://2captcha.com/res.php"

    def _submit(self, data: dict) -> str:
        """Submit a captcha for solving.  Returns the task ID."""
        data.update({"key": self.API_KEY, "json": 1})
        res = requests.post(self.SUBMIT_URL, data=data, timeout=30)
        res.raise_for_status()
        payload = res.json()
        if payload.get("status") != 1:
            raise RuntimeError(f"2Captcha submit failed: {payload}")
        return payload["request"]

    def _poll(self, task_id: str, max_wait: int = 120) -> str:
        """Poll 2Captcha for the result.  Returns the solution token."""
        for _ in range(max_wait):
            res = requests.get(self.POLL_URL, params={
                "key": self.API_KEY,
                "action": "get",
                "id": task_id,
                "json": 1,
            }, timeout=15)
            res.raise_for_status()
            payload = res.json()
            if payload.get("status") == 1:
                return payload["request"]
            if payload.get("request") not in ("CAPCHA_NOT_READY", "ERROR_NO_USER_CAPTCHA"):
                raise RuntimeError(f"2Captcha poll failed: {payload}")
            time.sleep(5)
        raise TimeoutError("Timeout waiting for captcha to be solved")

    def solve_recaptcha_v2(self, site_key: str, site_url: str) -> str:
        """Solve a Google reCAPTCHA v2 challenge.  Returns the token."""
        task_id = self._submit({
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": site_url,
        })
        return self._poll(task_id)

    def solve_hcaptcha(self, site_key: str, site_url: str) -> str:
        """Solve an hCaptcha challenge.  Returns the token."""
        task_id = self._submit({
            "method": "hcaptcha",
            "sitekey": site_key,
            "pageurl": site_url,
        })
        return self._poll(task_id)