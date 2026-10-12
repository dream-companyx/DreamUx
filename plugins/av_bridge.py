"""Мост к антивирусу главной ОС."""

import os
import shutil
import platform
import subprocess
import datetime


PLATFORM = platform.system()


class AVBridge:
    def __init__(self, log_fn=None):
        self.log_fn = log_fn or (lambda m: None)
        self.host_av = self._detect_host_av()
        self.log_fn(f"[AV-BRIDGE] Антивирус хоста: {self.host_av or 'не найден'}")
        self._fallback = None
        if self.host_av is None:
            try:
                from antivirus import Antivirus
                self._fallback = Antivirus(log_fn=log_fn)
                self.log_fn("[AV-BRIDGE] Fallback: встроенный антивирус")
            except ImportError:
                pass

    def _detect_host_av(self):
        if PLATFORM == "Windows":
            for p in [
                r"C:\Program Files\Windows Defender\MpCmdRun.exe",
                r"C:\Program Files (x86)\Windows Defender\MpCmdRun.exe",
            ]:
                if os.path.isfile(p):
                    return {"name": "Windows Defender", "path": p, "type": "defender"}
            base = r"C:\ProgramData\Microsoft\Windows Defender\Platform"
            if os.path.isdir(base):
                for root, _, files in os.walk(base):
                    if "MpCmdRun.exe" in files:
                        return {"name": "Windows Defender",
                                "path": os.path.join(root, "MpCmdRun.exe"),
                                "type": "defender"}
        elif PLATFORM == "Linux":
            for cmd in ["clamscan", "clamdscan"]:
                p = shutil.which(cmd)
                if p:
                    return {"name": "ClamAV", "path": p, "type": "clamav"}
        return None

    def scan(self, path: str) -> dict:
        if not os.path.isfile(path):
            return {"error": "not a file"}
        if self.host_av:
            t = self.host_av["type"]
            if t == "defender":
                return self._scan_defender(path)
            if t == "clamav":
                return self._scan_clamav(path)
        if self._fallback:
            r = self._fallback.scan(path)
            r["source"] = "builtin"
            return r
        return {"verdict": "unknown", "issues": ["Нет AV"], "source": "none"}

    def _scan_defender(self, path):
        try:
            cmd = [self.host_av["path"], "-Scan", "-ScanType", "3",
                   "-File", path, "-DisableRemediation"]
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, encoding="cp866", errors="replace",
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            if "no threats" in out.lower():
                verdict, issues = "clean", []
            elif "threat" in out.lower() or "virus" in out.lower():
                verdict = "malicious"
                issues = [l.strip() for l in out.splitlines()
                          if "threat" in l.lower() or "virus" in l.lower()]
                issues = issues[:5] or ["Defender обнаружил угрозу"]
            else:
                verdict, issues = "suspicious", [out.strip()[:200]]
            return {"verdict": verdict, "issues": issues, "source": "defender",
                    "scanned_at": datetime.datetime.now().isoformat(timespec="seconds")}
        except Exception as e:
            return {"verdict": "unknown", "issues": [f"Ошибка Defender: {e}"],
                    "source": "defender"}

    def _scan_clamav(self, path):
        try:
            cmd = [self.host_av["path"], "--no-summary", path]
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, encoding="utf-8", errors="replace",
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode == 0:
                verdict, issues = "clean", []
            elif proc.returncode == 1:
                verdict = "malicious"
                issues = [l.strip() for l in out.splitlines() if "FOUND" in l]
            else:
                verdict, issues = "unknown", [out.strip()[:200]]
            return {"verdict": verdict, "issues": issues, "source": "clamav",
                    "scanned_at": datetime.datetime.now().isoformat(timespec="seconds")}
        except Exception as e:
            return {"verdict": "unknown", "issues": [f"Ошибка ClamAV: {e}"],
                    "source": "clamav"}

    def status(self):
        if self.host_av:
            return {"active": True, "name": self.host_av["name"],
                    "path": self.host_av["path"], "type": self.host_av["type"]}
        if self._fallback:
            return {"active": True, "name": "DreamUX Builtin AV",
                    "type": "builtin"}
        return {"active": False, "name": "none"}
