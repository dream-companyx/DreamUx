# -*- coding: utf-8 -*-
"""DRXFS — DreamUX File System. Файловая система внутри VHD."""

import os
import struct
import datetime
import threading


DRXFS_MAGIC = b"DRXFS\x01\x00\x00"
DRXFS_VERSION = 1
VHD_FOOTER_SIZE = 512
DRXFS_HEADER_SIZE = 512
DRXFS_ENTRY_SIZE = 512
DRXFS_DATA_ALIGN = 4096
DRXFS_HEADER_OFFSET = VHD_FOOTER_SIZE
DRXFS_TABLE_OFFSET = DRXFS_HEADER_OFFSET + DRXFS_HEADER_SIZE
FLAG_DIR = 1


class DrxFSException(Exception):
    pass


def _align_up(value, align):
    return ((value + align - 1) // align) * align


def _timestamp():
    return int(datetime.datetime.now().timestamp())


def _human_size(n):
    for u in ["Б", "КБ", "МБ", "ГБ"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} ТБ"


class DrxFS:
    def __init__(self, vhd_path, log_fn=None):
        self.path = os.path.abspath(vhd_path)
        self.log = log_fn or (lambda m: None)
        self._lock = threading.RLock()
        self.files = {}
        if not os.path.isfile(self.path):
            raise DrxFSException(f"VHD не найден: {self.path}")
        self._open()

    def _open(self):
        with open(self.path, "rb") as f:
            f.seek(DRXFS_HEADER_OFFSET)
            magic = f.read(8)
        if magic == DRXFS_MAGIC:
            self._load()
        else:
            self._format()

    def _format(self):
        self.files = {}
        with open(self.path, "r+b") as f:
            f.seek(0, 2)
            size = f.tell()
            need = DRXFS_TABLE_OFFSET + DRXFS_ENTRY_SIZE
            if size < need:
                f.write(b"\x00" * (need - size))
            f.seek(DRXFS_HEADER_OFFSET)
            header = bytearray(DRXFS_HEADER_SIZE)
            header[0:8] = DRXFS_MAGIC
            struct.pack_into("<I", header, 8, DRXFS_VERSION)
            struct.pack_into("<I", header, 12, 0)
            struct.pack_into("<Q", header, 16, DRXFS_TABLE_OFFSET)
            struct.pack_into("<Q", header, 24, 0)
            struct.pack_into("<Q", header, 32, _timestamp())
            f.write(bytes(header))
            f.seek(DRXFS_TABLE_OFFSET)
            f.write(b"\x00" * DRXFS_ENTRY_SIZE)
        self.log(f"[DRXFS] ✅ Форматирован: {os.path.basename(self.path)}")

    def _load(self):
        with open(self.path, "rb") as f:
            f.seek(DRXFS_HEADER_OFFSET)
            header = f.read(DRXFS_HEADER_SIZE)
            if len(header) < 40:
                self.files = {}
                return
            file_count = struct.unpack_from("<I", header, 12)[0]
            table_offset = struct.unpack_from("<Q", header, 16)[0]
            if file_count > 100000:
                self._format()
                return
            self.files = {}
            f.seek(table_offset)
            for i in range(file_count):
                entry = f.read(DRXFS_ENTRY_SIZE)
                if len(entry) < DRXFS_ENTRY_SIZE:
                    break
                name_len = struct.unpack_from("<H", entry, 0)[0]
                flags = struct.unpack_from("<H", entry, 2)[0]
                size = struct.unpack_from("<Q", entry, 4)[0]
                offset = struct.unpack_from("<Q", entry, 12)[0]
                created = struct.unpack_from("<Q", entry, 20)[0]
                modified = struct.unpack_from("<Q", entry, 28)[0]
                if name_len == 0 or name_len > 400:
                    continue
                try:
                    name = entry[36:36 + name_len].decode("utf-8")
                except Exception:
                    continue
                self.files[name] = {
                    "size": size, "offset": offset,
                    "is_dir": bool(flags & FLAG_DIR),
                    "created": created, "modified": modified,
                }

    def _save(self):
        with self._lock:
            try:
                file_count = len(self.files)
                table_size = (file_count + 1) * DRXFS_ENTRY_SIZE
                data_start = _align_up(
                    DRXFS_TABLE_OFFSET + table_size, DRXFS_DATA_ALIGN
                )
                offset = data_start
                for name, info in self.files.items():
                    info["offset"] = offset
                    if not info["is_dir"]:
                        offset += info["size"]
                        offset = _align_up(offset, DRXFS_DATA_ALIGN)
                total_size = offset
                with open(self.path, "r+b") as f:
                    f.seek(0, 2)
                    cur = f.tell()
                    if cur < total_size:
                        f.write(b"\x00" * (total_size - cur))
                    f.seek(DRXFS_HEADER_OFFSET)
                    header = bytearray(DRXFS_HEADER_SIZE)
                    header[0:8] = DRXFS_MAGIC
                    struct.pack_into("<I", header, 8, DRXFS_VERSION)
                    struct.pack_into("<I", header, 12, file_count)
                    struct.pack_into("<Q", header, 16, DRXFS_TABLE_OFFSET)
                    struct.pack_into("<Q", header, 24, data_start)
                    struct.pack_into("<Q", header, 32, _timestamp())
                    f.write(bytes(header))
                    f.seek(DRXFS_TABLE_OFFSET)
                    for name, info in self.files.items():
                        entry = bytearray(DRXFS_ENTRY_SIZE)
                        name_bytes = name.encode("utf-8")
                        name_len = min(len(name_bytes), 400)
                        struct.pack_into("<H", entry, 0, name_len)
                        struct.pack_into("<H", entry, 2,
                                         FLAG_DIR if info["is_dir"] else 0)
                        struct.pack_into("<Q", entry, 4, info["size"])
                        struct.pack_into("<Q", entry, 12, info["offset"])
                        struct.pack_into("<Q", entry, 20, info.get("created", 0))
                        struct.pack_into("<Q", entry, 28, info.get("modified", 0))
                        entry[36:36 + name_len] = name_bytes[:name_len]
                        f.write(bytes(entry))
                    f.write(b"\x00" * DRXFS_ENTRY_SIZE)
                    return True
            except Exception as e:
                self.log(f"[DRXFS] ⛔ save: {e}")
                return False

    def list_dir(self, inner_dir=""):
        with self._lock:
            prefix = inner_dir.strip("/")
            if prefix:
                prefix += "/"
            result = []
            seen = set()
            for name in self.files:
                if not name.startswith(prefix):
                    continue
                rest = name[len(prefix):]
                if not rest:
                    continue
                parts = rest.split("/", 1)
                if len(parts) == 1:
                    info = self.files[name]
                    result.append(
                        ("dir" if info["is_dir"] else "file",
                         parts[0], info["size"])
                    )
                else:
                    if parts[0] not in seen:
                        seen.add(parts[0])
                        result.append(("dir", parts[0], 0))
            return sorted(result, key=lambda x: (x[0] != "dir", x[1].lower()))

    def exists(self, inner_path):
        inner_path = inner_path.strip("/")
        if inner_path in self.files:
            return True
        prefix = inner_path + "/"
        return any(n.startswith(prefix) for n in self.files)

    def is_dir(self, inner_path):
        info = self.files.get(inner_path.strip("/"))
        return bool(info and info["is_dir"])

    def read(self, inner_path):
        with self._lock:
            inner_path = inner_path.strip("/")
            info = self.files.get(inner_path)
            if not info or info["is_dir"]:
                return None
            try:
                with open(self.path, "rb") as f:
                    f.seek(info["offset"])
                    return f.read(info["size"])
            except Exception as e:
                self.log(f"[DRXFS] read {inner_path}: {e}")
                return None

    def write(self, inner_path, data):
        with self._lock:
            inner_path = inner_path.strip("/").replace("\\", "/")
            if not inner_path:
                return False
            if isinstance(data, str):
                data = data.encode("utf-8")
            parts = inner_path.split("/")
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                if parent and parent not in self.files:
                    self.files[parent] = {
                        "size": 0, "offset": 0, "is_dir": True,
                        "created": _timestamp(),
                        "modified": _timestamp(),
                    }
            old = self.files.get(inner_path)
            self.files[inner_path] = {
                "size": len(data), "offset": 0, "is_dir": False,
                "created": old["created"] if old else _timestamp(),
                "modified": _timestamp(),
            }
            if not self._save():
                return False
            try:
                with open(self.path, "r+b") as f:
                    f.seek(self.files[inner_path]["offset"])
                    f.write(data)
                return True
            except Exception as e:
                self.log(f"[DRXFS] write {inner_path}: {e}")
                return False

    def mkdir(self, inner_path):
        with self._lock:
            inner_path = inner_path.strip("/").replace("\\", "/")
            if not inner_path:
                return False
            if inner_path in self.files:
                return True
            self.files[inner_path] = {
                "size": 0, "offset": 0, "is_dir": True,
                "created": _timestamp(), "modified": _timestamp(),
            }
            return self._save()

    def delete(self, inner_path):
        with self._lock:
            inner_path = inner_path.strip("/")
            prefix = inner_path + "/"
            to_del = [n for n in self.files
                      if n == inner_path or n.startswith(prefix)]
            if not to_del:
                return False
            for n in to_del:
                del self.files[n]
            return self._save()

    def stats(self):
        with self._lock:
            files = [n for n, i in self.files.items() if not i["is_dir"]]
            dirs = [n for n, i in self.files.items() if i["is_dir"]]
            used = sum(self.files[n]["size"] for n in files)
            try:
                real_size = os.path.getsize(self.path)
            except Exception:
                real_size = 0
            return {
                "files": len(files), "dirs": len(dirs),
                "used_bytes": used, "used_human": _human_size(used),
                "file_size": real_size,
                "file_size_human": _human_size(real_size),
            }
