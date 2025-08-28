# core/captcha.py
import os, time, requests

class CaptchaSolver:
    """
    Minimal 2Captcha client. Supports:
      - reCAPTCHA v2 (checkbox/invisible): method=userrecaptcha
      - hCaptcha: method=hcaptcha

    Env:
      CAPTCHA_PROVIDER=2captcha
      CAPTCHA_API_KEY=<your key>
      CAPTCHA_MAX_WAIT=180  (seconds)
      CAPTCHA_POLL_EVERY=5  (seconds)
    """
    def __init__(self):
        self.provider = (os.getenv("CAPTCHA_PROVIDER") or "").lower()
        self.api_key = os.getenv("CAPTCHA_API_KEY")
        self.max_wait = int(os.getenv("CAPTCHA_MAX_WAIT", "180"))
        self.poll_every = int(os.getenv("CAPTCHA_POLL_EVERY", "5"))

    def available(self) -> bool:
        return self.provider == "2captcha" and bool(self.api_key)

    # ---------- 2Captcha ----------
    def _2captcha_submit(self, method: str, sitekey: str, url: str, invisible: bool = False):
        payload = {
            "key": self.api_key,
            "method": method,  # "userrecaptcha" or "hcaptcha"
            "googlekey" if method == "userrecaptcha" else "sitekey": sitekey,
            "pageurl": url,
            "json": 1,
        }
        if method == "userrecaptcha" and invisible:
            payload["invisible"] = 1
        r = requests.post("https://2captcha.com/in.php", data=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != 1:
            raise RuntimeError(f"2captcha submit failed: {data}")
        return data["request"]  # request id

    def _2captcha_poll(self, req_id: str):
        start = time.time()
        while time.time() - start < self.max_wait:
            time.sleep(self.poll_every)
            r = requests.get("https://2captcha.com/res.php",
                             params={"key": self.api_key, "action": "get", "id": req_id, "json": 1},
                             timeout=30)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == 1:
                return data["request"]  # g-recaptcha-response or h-captcha-response
            elif data.get("request") in ("CAPCHA_NOT_READY", "ERROR_NO_SLOT_AVAILABLE"):
                continue
            else:
                raise RuntimeError(f"2captcha solve failed: {data}")
        raise TimeoutError("2captcha timed out")

    def solve_recaptcha_v2(self, sitekey: str, page_url: str, invisible=False) -> str:
        if not self.available():
            raise RuntimeError("Captcha solver not available")
        req_id = self._2captcha_submit("userrecaptcha", sitekey, page_url, invisible=invisible)
        return self._2captcha_poll(req_id)

    def solve_hcaptcha(self, sitekey: str, page_url: str) -> str:
        if not self.available():
            raise RuntimeError("Captcha solver not available")
        req_id = self._2captcha_submit("hcaptcha", sitekey, page_url)
        return self._2captcha_poll(req_id)
