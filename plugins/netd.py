"""
NetDaemon — сетевой демон ядра SimpleOS.
Мульти-сессии (браузер, игры, установщики), токены, allowlist, VPN.
"""

import hmac
import secrets
import time
import ssl
import urllib.request
import urllib.error
from urllib.parse import urlparse


class NetDaemon:
    def __init__(self, log_fn=None, ovpn=None):
        self._aes_key = secrets.token_bytes(32)
        self._sessions = {}
        self.rate_limit_sec = 0.05
        self._last_request = 0.0
        self.log_fn = log_fn or (lambda m: None)
        self.default_allowlist = set()
        self.ovpn = ovpn
        self.require_vpn = False
        self.log_fn("[NETD] Ядро запущено")

    # --- Сессии ---
    def issue_session(self, client_name, allowlist=None, require_vpn=None):
        token = secrets.token_urlsafe(48)
        self._sessions[token] = {
            "client": client_name,
            "issued_at": time.time(),
            "requests": 0,
            "allowlist": set(allowlist) if allowlist else set(),
            "require_vpn": self.require_vpn if require_vpn is None else require_vpn,
        }
        self.log_fn(f"[NETD] Токен выдан '{client_name}'")
        return token

    def revoke_session(self, token):
        s = self._sessions.pop(token, None)
        if s:
            self.log_fn(f"[NETD] Токен отозван '{s['client']}'")

    def revoke_all(self):
        for t in list(self._sessions.keys()):
            self.revoke_session(t)

    def revoke_by_client(self, client_name):
        for t in list(self._sessions.keys()):
            if self._sessions[t]["client"] == client_name:
                self.revoke_session(t)

    # --- Проверки ---
    def _get_session(self, token):
        if not token:
            return None
        for t, s in self._sessions.items():
            if hmac.compare_digest(t, token):
                return s
        return None

    def _check_domain(self, session, url):
        allow = session.get("allowlist") or self.default_allowlist
        if not allow:
            return True
        host = (urlparse(url).hostname or "").lower()
        for a in allow:
            a = a.lower()
            if host == a or host.endswith("." + a):
                return True
        return False

    def _rate_limit(self):
        dt = time.time() - self._last_request
        if dt < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - dt)
        self._last_request = time.time()

    def _vpn_ready(self, session):
        if session.get("require_vpn") and self.ovpn is not None:
            if not self.ovpn.is_connected():
                self.log_fn(f"[NETD] ⛔ Kill-switch: VPN не подключён")
                return False
        return True

    def _build_opener(self):
        handlers = []
        if self.ovpn is not None and self.ovpn.is_connected():
            proxy = self.ovpn.http_proxy()
            if proxy:
                handlers.append(urllib.request.ProxyHandler(
                    {"http": proxy, "https": proxy}
                ))
        ctx = ssl.create_default_context()
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
        return urllib.request.build_opener(*handlers)

    # --- Запрос ---
    def request(self, token, method, url, headers=None, body=None, timeout=15):
        session = self._get_session(token)
        if not session:
            self.log_fn("[NETD] Отказ: неверный токен")
            return {"error": "invalid token"}
        if not self._check_domain(session, url):
            self.log_fn(f"[NETD] Отказ ({session['client']}): домен не в allowlist")
            return {"error": "domain not allowed"}
        if not self._vpn_ready(session):
            return {"error": "vpn not connected (kill-switch)"}

        self._rate_limit()
        try:
            req = urllib.request.Request(
                url, data=body, method=method.upper(), headers=headers or {}
            )
            opener = self._build_opener()
            with opener.open(req, timeout=timeout) as r:
                raw = r.read()
                status = r.status
                resp_headers = dict(r.headers.items())
        except urllib.error.HTTPError as e:
            raw = e.read()
            status = e.code
            resp_headers = dict(e.headers.items()) if e.headers else {}
        except Exception as e:
            self.log_fn(f"[NETD] Ошибка ({session['client']}): {e}")
            return {"error": str(e)}

        session["requests"] += 1
        n = session["requests"]
        via = "VPN" if self.ovpn and self.ovpn.is_connected() else "direct"
        self.log_fn(f"[NETD] [{session['client']}]#{n} via={via} "
                    f"{method} {urlparse(url).hostname} → {status} "
                    f"({len(raw)} байт)")
        return {"status": status, "headers": resp_headers, "body": raw}


_GLOBAL = None
def get_global_daemon():
    return _GLOBAL
def set_global_daemon(d):
    global _GLOBAL
    _GLOBAL = d