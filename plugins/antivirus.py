"""
Встроенный антивирус ядра SimpleOS (fallback).
Работает локально: хэши, расширения, строки, эвристика, энтропия.
"""

import os
import re
import json
import math
import hashlib
import datetime
from collections import Counter


KNOWN_MALICIOUS_HASHES = {
    "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f":
        "EICAR-Test-File",
}

DANGEROUS_EXT = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".pif",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".ps1", ".psm1", ".jar", ".class",
    ".sh", ".run", ".bin", ".app", ".apk", ".ipa",
    ".dll", ".so", ".dylib",
}

DOUBLE_EXT = [
    ".txt.exe", ".jpg.exe", ".pdf.exe", ".doc.exe",
    ".mp3.exe", ".mp4.exe", ".png.exe",
    ".txt.scr", ".pdf.scr", ".doc.scr",
    ".jpg.vbs", ".pdf.js", ".doc.bat",
]

MALICIOUS_STRINGS = [
    "your files have been encrypted", "your files are encrypted",
    "send bitcoin", "decrypt your files", "readme_decrypt",
    "ransom", "getasynckeystate", "setwindowshookex", "keylog",
    "reverse shell", "bind shell", "nc -e /bin/sh", "meterpreter",
    "stratum+tcp://", "xmrig", "minerd", "cryptonight",
    "urllib.request.urlretrieve", "invoke-webrequest", "downloadstring",
    "bitsadmin /transfer", "currentversion\\run", "schtasks /create",
    "systemctl enable", "crontab -e",
    "base64 -d", "frombase64string", "eval(base64", "exec(base64",
    "powershell -enc", "powershell -e ",
    "mimikatz", "lsass.exe", "hashdump",
]

HEURISTIC_REGEX = [
    (re.compile(rb"MZ\x90\x00"), "PE-заголовок (Windows EXE)"),
    (re.compile(rb"\x7fELF"), "ELF-заголовок (Linux ELF)"),
    (re.compile(rb"PK\x03\x04"), "ZIP-архив (возможно APK/JAR/DOCX)"),
    (re.compile(rb"#!"), "Shebang (исполняемый скрипт)"),
    (re.compile(rb"<script[^>]*>.*eval\(", re.I | re.S), "JS с eval()"),
    (re.compile(rb"powershell\s+-(enc|e)\s", re.I), "PowerShell -enc"),
    (re.compile(rb"cmd\.exe\s+/c", re.I), "Вызов cmd.exe /c"),
    (re.compile(rb"rundll32\s+javascript:", re.I), "rundll32 javascript"),
    (re.compile(rb"mshta\s+http", re.I), "mshta с URL"),
]


class Antivirus:
    def __init__(self, log_fn=None, db_path=None):
        self.log_fn = log_fn or (lambda m: None)
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), "..", "avdb"
        )
        os.makedirs(self.db_path, exist_ok=True)
        self.hashes = dict(KNOWN_MALICIOUS_HASHES)
        self.version = 1
        self.updated_at = None
        self._load_db()
        self.log_fn(f"[AV] сигнатур: {len(self.hashes)}")

    def _load_db(self):
        p = os.path.join(self.db_path, "hashes.json")
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.hashes.update(d.get("hashes", {}))
                self.version = d.get("version", 1)
                self.updated_at = d.get("updated_at")
            except Exception as e:
                self.log_fn(f"[AV] загрузка: {e}")

    def save_db(self):
        p = os.path.join(self.db_path, "hashes.json")
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"version": self.version,
                           "updated_at": self.updated_at,
                           "hashes": self.hashes}, f, indent=2)
        except Exception as e:
            self.log_fn(f"[AV] сохранение: {e}")

    def sha256(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _entropy(self, data):
        if not data:
            return 0.0
        counts = Counter(data)
        n = len(data)
        e = 0.0
        for c in counts.values():
            p = c / n
            e -= p * math.log2(p)
        return e

    def _check_ext(self, path):
        issues = []
        name = os.path.basename(path).lower()
        for ext in DANGEROUS_EXT:
            if name.endswith(ext):
                issues.append(f"Опасное расширение {ext}")
                break
        for de in DOUBLE_EXT:
            if name.endswith(de):
                issues.append(f"Двойное расширение {de}")
                break
        return issues

    def _check_strings(self, data):
        text = data.decode("utf-8", errors="replace").lower()
        return [f"сигнатура: {s!r}" for s in MALICIOUS_STRINGS if s in text]

    def _check_heuristics(self, data):
        return [f"эвристика: {d}" for r, d in HEURISTIC_REGEX
                if r.search(data[:65536])]

    def _check_entropy(self, data):
        e = self._entropy(data[:65536])
        if e > 7.5:
            return [f"высокая энтропия ({e:.2f})"]
        return []

    def scan(self, path):
        if not os.path.isfile(path):
            return {"error": "not a file"}
        size = os.path.getsize(path)
        try:
            sha = self.sha256(path)
        except Exception as e:
            return {"error": f"hash: {e}"}

        if sha in self.hashes:
            return {"path": path, "sha256": sha, "size": size,
                    "verdict": "malicious",
                    "issues": [f"Известный вредонос: {self.hashes[sha]}"],
                    "scanned_at": datetime.datetime.now().isoformat(timespec="seconds")}

        issues = self._check_ext(path)
        data = b""
        try:
            with open(path, "rb") as f:
                data = f.read(1024 * 1024)
        except Exception:
            pass
        issues += self._check_strings(data)
        issues += self._check_heuristics(data)
        issues += self._check_entropy(data)

        if any("сигнатура" in i.lower() or "вредонос" in i.lower() for i in issues):
            verdict = "malicious"
        elif issues:
            verdict = "suspicious"
        else:
            verdict = "clean"

        return {"path": path, "sha256": sha, "size": size,
                "verdict": verdict, "issues": issues,
                "scanned_at": datetime.datetime.now().isoformat(timespec="seconds")}