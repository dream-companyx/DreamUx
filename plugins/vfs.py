"""DreamUX VFS — обёртка над DRXFS."""

import os
import json

from plugins.drxfs import DrxFS, DrxFSException


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
VFS_ROOT = os.path.join(KERNEL_DIR, "vfs")
VFS_CONFIG = os.path.join(VFS_ROOT, "disks.json")


DISKS = {
    "disk0": {"name": "СИСТЕМА", "file": os.path.join(VFS_ROOT, "disk0.vhd")},
    "disk1": {"name": "ЗАГРУЗОЧНЫЙ", "file": os.path.join(VFS_ROOT, "disk1.vhd")},
    "disk2": {"name": "ОСТАЛЬНОЕ", "file": os.path.join(VFS_ROOT, "disk2.vhd")},
}

_cache = {}


def _fs(disk_key):
    disk_key = disk_key.lower()
    if disk_key not in DISKS:
        raise DrxFSException(f"Нет диска: {disk_key}")
    if disk_key not in _cache:
        path = DISKS[disk_key]["file"]
        if not os.path.isfile(path):
            raise DrxFSException(f"VHD не найден: {path}")
        _cache[disk_key] = DrxFS(path)
    return _cache[disk_key]


def is_initialized():
    return os.path.isfile(VFS_CONFIG)


def list_disks():
    return list(DISKS.keys())


def read(disk_key, inner_path):
    return _fs(disk_key).read(inner_path)


def write(disk_key, inner_path, data):
    return _fs(disk_key).write(inner_path, data)


def list_dir(disk_key, inner_dir=""):
    return _fs(disk_key).list_dir(inner_dir)


def mkdir(disk_key, inner_path):
    return _fs(disk_key).mkdir(inner_path)


def delete(disk_key, inner_path):
    return _fs(disk_key).delete(inner_path)


def exists(disk_key, inner_path):
    return _fs(disk_key).exists(inner_path)


def is_dir(disk_key, inner_path):
    return _fs(disk_key).is_dir(inner_path)


def copy_local_to_vfs(disk_key, local_path, inner_path):
    if not os.path.isfile(local_path):
        return False
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        return write(disk_key, inner_path, data)
    except Exception:
        return False


def copy_vfs_to_local(disk_key, inner_path, local_path):
    data = read(disk_key, inner_path)
    if data is None:
        return False
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def copy_dir_local_to_vfs(disk_key, local_dir, inner_dir, log_fn=None):
    log = log_fn or (lambda m: None)
    if not os.path.isdir(local_dir):
        return 0
    count = 0
    for root, dirs, files in os.walk(local_dir):
        rel = os.path.relpath(root, local_dir)
        if rel == ".":
            rel = ""
        vfs_dir = (inner_dir + "/" + rel).strip("/") if rel else inner_dir
        if vfs_dir:
            mkdir(disk_key, vfs_dir)
        for name in files:
            src = os.path.join(root, name)
            dst = (vfs_dir + "/" + name).strip("/") if vfs_dir else name
            if copy_local_to_vfs(disk_key, src, dst):
                count += 1
                log(f"  → {dst}")
    return count


def _human_size(n):
    for u in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} ПБ"


def format_info():
    lines = ["DreamUX VFS (DRXFS)"]
    for key, info in DISKS.items():
        path = info["file"]
        lines.append(f"\n💾 {key}: {info['name']}")
        lines.append(f"   VHD:  {path}")
        if os.path.isfile(path):
            try:
                st = _fs(key).stats()
                lines.append(f"   Файлов: {st['files']}")
                lines.append(f"   Папок:  {st['dirs']}")
                lines.append(f"   Занято: {st['used_human']}")
                lines.append(f"   Размер: {st['file_size_human']}")
            except Exception as e:
                lines.append(f"   ⚠ {e}")
        else:
            lines.append(f"   ❌ НЕ СОЗДАН")
    return "\n".join(lines)


def slash_vfs(kernel, args):
    if not args:
        print("DreamUX VFS (DRXFS)")
        print("  /vfs info")
        print("  /vfs ls <disk> <path>")
        print("  /vfs cat <disk> <path>")
        print("  /vfs write <disk> <path> <text>")
        print("  /vfs mkdir <disk> <path>")
        print("  /vfs rm <disk> <path>")
        return
    cmd = args[0].lower()
    if cmd == "info":
        print(format_info())
        return
    if len(args) < 3:
        print("Использование: /vfs <cmd> <disk> <path> [text]")
        return
    disk = args[1].lower()
    path = args[2]
    if disk not in DISKS:
        print(f"Нет диска: {disk}")
        return
    if cmd == "ls":
        items = list_dir(disk, path)
        if not items:
            print("(пусто)")
            return
        for kind, name, size in items:
            icon = "📁" if kind == "dir" else "📄"
            sz = f" ({size} Б)" if kind == "file" else ""
            print(f"  {icon} {name}{sz}")
        return
    if cmd == "cat":
        data = read(disk, path)
        if data is None:
            print("Не найдено")
            return
        try:
            print(data.decode("utf-8"))
        except Exception:
            print(f"<бинарные, {len(data)} байт>")
        return
    if cmd == "write":
        if len(args) < 4:
            print("Использование: /vfs write <disk> <path> <text>")
            return
        text = " ".join(args[3:])
        print("OK" if write(disk, path, text) else "FAIL")
        return
    if cmd == "mkdir":
        print("OK" if mkdir(disk, path) else "FAIL")
        return
    if cmd == "rm":
        print("OK" if delete(disk, path) else "FAIL")
        return
    print(f"Неизвестно: {cmd}")


def slash_disks(kernel, args):
    print(format_info())


def slash_disk(kernel, args):
    if not args:
        print("DreamUX VFS")
        print("  /disks  — список")
        print("  /vfs    — файлы")
        return
    print(f"Неизвестно: {args[0]}")


def register(kernel):
    kernel.register_slash_command("vfs", slash_vfs, "DreamUX VFS (DRXFS)")
    kernel.register_slash_command("disks", slash_disks, "Список дисков")
    kernel.register_slash_command("disk", slash_disk, "VFS инфо")
    return []
