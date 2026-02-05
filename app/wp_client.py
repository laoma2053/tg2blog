import base64
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass
class WpPost:
    post_id: int
    link: Optional[str]


class WpClient:
    def __init__(self, base: str, user: str, app_pwd: str, verify_tls: bool = True, timeout: int = 20):
        self.base = base.rstrip("/")
        self.user = user
        self.app_pwd = app_pwd
        self.verify_tls = verify_tls
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        # Basic Auth: user:app_password (app password may contain spaces; WP expects it without spaces)
        pwd = self.app_pwd.replace(" ", "")
        token = base64.b64encode(f"{self.user}:{pwd}".encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }

    def create_post(self, title: str, content: str, slug: Optional[str] = None, status: str = "publish") -> WpPost:
        url = f"{self.base}/wp-json/wp/v2/posts"
        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
        }
        if slug:
            payload["slug"] = slug

        r = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout, verify=self.verify_tls)
        if r.status_code >= 300:
            raise RuntimeError(f"WP create_post failed: {r.status_code} {r.text[:500]}")
        data = r.json()
        return WpPost(post_id=int(data["id"]), link=data.get("link"))

    def update_post(self, post_id: int, title: str, content: str, slug: Optional[str] = None) -> WpPost:
        url = f"{self.base}/wp-json/wp/v2/posts/{post_id}"
        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
        }
        if slug:
            payload["slug"] = slug

        r = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout, verify=self.verify_tls)
        if r.status_code >= 300:
            raise RuntimeError(f"WP update_post failed: {r.status_code} {r.text[:500]}")
        data = r.json()
        return WpPost(post_id=int(data["id"]), link=data.get("link"))