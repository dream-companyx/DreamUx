"""DreamUX Archive Paket — модуль .duap."""

import os
import io
import json
import zipfile
import hashlib
import datetime


DUAP_MAGIC = b"DUAP"
DUAP_VERSION = 1
DUAP_HEADER_SIZE = 64


def create_duap(zip_path, duap_path, manifest=None, log=print):
    if not os.path.isfile(zip_path):
        log(f"[DUAP] ⛔ Нет ZIP: {zip_path}")
        return False

    with open(zip_path, "rb") as f:
        zip_data = f.read()

    sha = hashlib.sha256(zip_data).digest()

    if manifest is None:
        manifest = {}
    manifest.setdefault("created_at",
                        datetime.datetime.now().isoformat(timespec="seconds"))
    manifest.setdefault("size", len(zip_data))
    manifest.setdefault("sha256", sha.hex())
    manifest.setdefault("files", [])

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zf:
            for name in zf.namelist():
                info = zf.getinfo(name)
                file_data = zf.read(name)
                manifest["files"].append({
                    "name": name,
                    "size": info.file_size,
                    "sha256": hashlib.sha256(file_data).hexdigest(),
                })
    except Exception as e:
        log(f"[DUAP] manifest: {e}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf_out:
        zf_out.writestr("manifest.duap",
                        json.dumps(manifest, indent=2, ensure_ascii=False))
        with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zf_in:
            for name in zf_in.namelist():
                if name == "manifest.duap":
                    continue
                zf_out.writestr(name, zf_in.read(name))

    new_zip = buf.getvalue()
    new_sha = hashlib.sha256(new_zip).digest()

    header = bytearray(DUAP_HEADER_SIZE)
    header[0:4] = DUAP_MAGIC
    header[4:8] = DUAP_VERSION.to_bytes(4, "little")
    header[8:12] = (0).to_bytes(4, "little")
    header[12:44] = new_sha

    with open(duap_path, "wb") as f:
        f.write(bytes(header))
        f.write(new_zip)

    log(f"[DUAP] ✅ Создан: {duap_path}")
    log(f"[DUAP] SHA256: {new_sha.hex()[:16]}...")
    log(f"[DUAP] Файлов: {len(manifest['files'])}")
    return True


def is_duap(path):
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as f:
            return f.read(4) == DUAP_MAGIC
    except Exception:
        return False


def is_zip(path):
    return zipfile.is_zipfile(path)


def detect_format(path):
    if is_duap(path):
        return "duap"
    if is_zip(path):
        return "zip"
    return None


def read_duap_header(path):
    if not is_duap(path):
        return None
    with open(path, "rb") as f:
        h = f.read(DUAP_HEADER_SIZE)
    return {
        "version": int.from_bytes(h[4:8], "little"),
        "flags": int.from_bytes(h[8:12], "little"),
        "sha256": h[12:44].hex(),
    }


def verify_duap(path):
    if not is_duap(path):
        return False, "не .duap"
    with open(path, "rb") as f:
        h = f.read(DUAP_HEADER_SIZE)
        zip_data = f.read()
    expected = h[12:44]
    actual = hashlib.sha256(zip_data).digest()
    if expected != actual:
        return False, "SHA256 не совпадает"
    return True, "OK"


def open_duap(path):
    if not is_duap(path):
        raise ValueError("не .duap")
    with open(path, "rb") as f:
        f.seek(DUAP_HEADER_SIZE)
        data = f.read()
    return zipfile.ZipFile(io.BytesIO(data), "r")


def read_manifest(path):
    try:
        with open_duap(path) as zf:
            return json.loads(zf.read("manifest.duap").decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def open_archive(path):
    fmt = detect_format(path)
    if fmt == "duap":
        return open_duap(path)
    elif fmt == "zip":
        return zipfile.ZipFile(path, "r")
    raise ValueError(f"Неизвестный формат: {path}")
