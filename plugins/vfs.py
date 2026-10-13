"""
DreamUX Virtual File System (VFS) — Вариант A.
VHD-контейнеры с данными в .vhd.data/

Slash-команды:
    /disk init             — создать диски (аккаунт + VHD)
    /disk 0 - 1 auto       — создать оба
    /disk remove 0|1|all   — удалить
    /disks                 — список
"""

import os
import sys
import json
import shutil
import struct
import hashlib
import datetime
import getpass


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
VFS_ROOT = os.path.join(KERNEL_DIR, "vfs")
VFS_CONFIG = os.path.join(VFS_ROOT, "disks.json")
USERS_FILE = os.path.join(KERNEL_DIR, "users.json")

DISK_0_VHD = os.path.join(VFS_ROOT, "disk0.vhd")
DISK_0_VHD_DATA = os.path.join(VFS_ROOT, "disk0.vhd.data")
DISK_0_SYSTEM = os.path.join(DISK_0_VHD_DATA, "system")
DISK_0_BOOT   = os.path.join(DISK_0_VHD_DATA, "boot")

DISK_1_VHD = os.path.join(VFS_ROOT, "disk1.vhd")
DISK_1_VHD_DATA = os.path.join(VFS_ROOT, "disk1.vhd.data")

DISK_0 = DISK_0_VHD_DATA
DISK_1 = DISK_1_VHD_DATA


VHD_FOOTER_COOKIE = b"conectix"
VHD_CREATOR_APP = b"drxu"
VHD_DISK_TYPE_DYNAMIC = 3
SECTOR_SIZE = 512

DISK_0_SIZE_GB = 2
DISK_1_SIZE_GB = 512


def _make_vhd_footer(current_size, original_size=0):
    if original_size == 0:
        original_size = current_size

    footer = bytearray(512)
    footer[0:8] = VHD_FOOTER_COOKIE
    struct.pack_into(">I", footer, 8, 0x00000002)
    struct.pack_into(">I", footer, 12, 0x00010000)
    struct.pack_into(">Q", footer, 16, 0xFFFFFFFFFFFFFFFF)

    import time
    ts = int(time.time()) - 946684800
    struct.pack_into(">I", footer, 24, ts)

    footer[28:32] = VHD_CREATOR_APP
    struct.pack_into(">I", footer, 32, 0x00010000)
    footer[36:40] = b"Wi2k"
    struct.pack_into(">Q", footer, 40, original_size)
    struct.pack_into(">Q", footer, 48, current_size)

    total_sectors = current_size // SECTOR_SIZE
    if total_sectors > 65535 * 16 * 255:
        total_sectors = 65535 * 16 * 255

    if total_sectors >= 65535 * 16 * 63:
        spt, heads = 255, 16
        cyl = total_sectors // (spt * heads)
    else:
        spt, heads = 17, 4
        cyl = total_sectors // (spt * heads)
        if cyl > 1024:
            spt, heads = 31, 16
            cyl = total_sectors // (spt * heads)
        if cyl > 16383:
            spt, heads = 63, 16
            cyl = 16383

    struct.pack_into(">H", footer, 56, cyl)
    footer[58] = heads
    footer[59] = spt
    struct.pack_into(">I", footer, 60, VHD_DISK_TYPE_DYNAMIC)
    struct.pack_into(">I", footer, 64, 0)

    total = sum(footer)
    checksum = (~total) & 0xFFFFFFFF
    struct.pack_into(">I", footer, 64, checksum)

    footer[68:84] = hashlib.md5(
        f"{datetime.datetime.now()}-{os.getpid()}".encode()
    ).digest()
    footer[84] = 0

    return bytes(footer)


def create_vhd_file(path, size_gb, log=print):
    size_bytes = size_gb * 1024 * 1024 * 1024
    size_bytes = (size_bytes // SECTOR_SIZE) * SECTOR_SIZE

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"\x00" * 512)
        footer = _make_vhd_footer(size_bytes)
        with open(path, "r+b") as f:
            f.seek(0)
            f.write(footer)
        log(f"[VHD] ✅ {os.path.basename(path)} ({size_gb} ГБ, динамический)")
        return True
    except Exception as e:
        log(f"[VHD] ⛔ {e}")
        return False


def _create_account(log=print):
    print("\n" + "=" * 60)
    print("  Создание аккаунта DreamUX")
    print("=" * 60)

    username = input(f"  Имя пользователя (Enter = {getpass.getuser()}): ").strip()
    if not username:
        username = getpass.getuser()

    while True:
        password = getpass.getpass("  Пароль: ")
        if len(password) < 4:
            print("  ⚠ Пароль минимум 4 символа")
            continue
        password2 = getpass.getpass("  Повторите: ")
        if password != password2:
            print("  ⚠ Пароли не совпадают")
            continue
        break

    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    users = {}
    if os.path.isfile(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)
        except Exception:
            pass

    users[username.lower()] = {
        "level": 0,
        "password_hash": password_hash,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    if "admin" not in users:
        users["admin"] = {"level": 1, "password_hash": None}
    if "guest" not in users:
        users["guest"] = {"level": 3, "password_hash": None}

    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        log(f"[ACCOUNT] ✅ '{username}' создан (уровень 0 SYSTEM)")
    except Exception as e:
        log(f"[ACCOUNT] ⛔ {e}")
        return None

    return username


def create_partition_0(log=print):
    log("\n[DISK] Создание Диска 0 — СИСТЕМА")

    create_vhd_file(DISK_0_VHD, DISK_0_SIZE_GB, log=log)

    os.makedirs(DISK_0_SYSTEM, exist_ok=True)
    os.makedirs(DISK_0_BOOT, exist_ok=True)

    for sub in ("kernel", "plugins", "config", "logs",
                "users", "assets", "bin", "lib", "system"):
        os.makedirs(os.path.join(DISK_0_SYSTEM, sub), exist_ok=True)

    for sub in ("boot", "recovery", "init", "splash", "efi"):
        os.makedirs(os.path.join(DISK_0_BOOT, sub), exist_ok=True)

    log(f"[DISK]   0.0 Система:     {DISK_0_SYSTEM}")
    log(f"[DISK]   0.5 Загрузочный: {DISK_0_BOOT}")

    src = os.path.join(KERNEL_DIR, "kernel.py")
    if os.path.isfile(src):
        try:
            shutil.copy2(src, os.path.join(DISK_0_SYSTEM, "kernel", "kernel.py"))
            log("[DISK]     ✅ kernel.py")
        except Exception:
            pass

    src = os.path.join(KERNEL_DIR, "plugins")
    if os.path.isdir(src):
        try:
            shutil.copytree(src, os.path.join(DISK_0_SYSTEM, "plugins"),
                            dirs_exist_ok=True)
            log("[DISK]     ✅ plugins/")
        except Exception:
            pass

    src = os.path.join(KERNEL_DIR, "version.json")
    if os.path.isfile(src):
        try:
            shutil.copy2(src, os.path.join(DISK_0_SYSTEM, "version.json"))
            log("[DISK]     ✅ version.json")
        except Exception:
            pass

    try:
        boot_cfg = os.path.join(DISK_0_BOOT, "boot", "boot.cfg")
        with open(boot_cfg, "w", encoding="utf-8") as f:
            f.write("# DreamUX Boot Configuration\n")
            f.write(f"# Created: {datetime.datetime.now()}\n\n")
            f.write("[Boot]\n")
            f.write("vhd = /vfs/disk0.vhd\n")
            f.write("kernel = /vfs/disk0.vhd.data/system/kernel/kernel.py\n")
            f.write("timeout = 5\n")
        log("[DISK]     ✅ boot.cfg")
    except Exception:
        pass

    return True


def create_partition_1(log=print):
    log("\n[DISK] Создание Диска 1 — ОСТАЛЬНОЕ")

    create_vhd_file(DISK_1_VHD, DISK_1_SIZE_GB, log=log)

    os.makedirs(DISK_1_VHD_DATA, exist_ok=True)
    for sub in ("home", "apps", "packages", "downloads",
                "snapshots", "sandbox", "users", "media", "tmp",
                "documents", "music", "pictures", "videos", "data"):
        os.makedirs(os.path.join(DISK_1_VHD_DATA, sub), exist_ok=True)
        log(f"[DISK]   ✅ {sub}/")

    return True


def is_initialized():
    return os.path.isfile(VFS_CONFIG)


def initialize_vfs(log=print):
    log("=" * 60)
    log("  DreamUX — первая инициализация")
    log("=" * 60)

    username = _create_account(log=log)
    if not username:
        return False

    try:
        os.makedirs(VFS_ROOT, exist_ok=True)
        create_partition_0(log)
        create_partition_1(log)

        config = {
            "version": 1,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "user": username,
            "format": "vhd",
            "disk_type": "dynamic",
            "partitions": {
                "0": {
                    "name": "СИСТЕМА", "type": "system",
                    "vhd": "vfs/disk0.vhd", "data": "vfs/disk0.vhd.data",
                    "size_gb": DISK_0_SIZE_GB, "dynamic": True,
                    "sub": {
                        "0.0": {"name": "Система", "path": "vfs/disk0.vhd.data/system"},
                        "0.5": {"name": "Загрузочный", "path": "vfs/disk0.vhd.data/boot"},
                    },
                },
                "1": {
                    "name": "ОСТАЛЬНОЕ", "type": "data",
                    "vhd": "vfs/disk1.vhd", "data": "vfs/disk1.vhd.data",
                    "size_gb": DISK_1_SIZE_GB, "dynamic": True,
                },
            },
        }

        with open(VFS_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        log(f"\n[DISK] ✅ Манифест: {VFS_CONFIG}")
        log("=" * 60)
        log("  ✅ ИНИЦИАЛИЗАЦИЯ ЗАВЕРШЕНА")
        log("=" * 60 + "\n")
        return True

    except Exception as e:
        log(f"[DISK] ⛔ {e}")
        return False


def get_partition_path(pid):
    if pid == "0":
        return DISK_0_VHD_DATA
    elif pid == "1":
        return DISK_1_VHD_DATA
    return None


def get_system_path(*sub):
    return os.path.join(DISK_0_SYSTEM, *sub)


def get_boot_path(*sub):
    return os.path.join(DISK_0_BOOT, *sub)


def get_data_path(*sub):
    return os.path.join(DISK_1_VHD_DATA, *sub)


def _dir_size(path):
    total = 0
    if not os.path.isdir(path):
        return 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _human_size(n):
    for u in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} ПБ"


def partition_info():
    info = []

    if os.path.isfile(DISK_0_VHD):
        info.append({
            "id": "0", "name": "СИСТЕМА", "type": "system",
            "vhd": DISK_0_VHD, "vhd_size": os.path.getsize(DISK_0_VHD),
            "data": DISK_0_VHD_DATA, "data_size": _dir_size(DISK_0_VHD_DATA),
            "size_gb": DISK_0_SIZE_GB, "icon": "💽",
            "sub": [
                {"id": "0.0", "name": "Система", "path": DISK_0_SYSTEM,
                 "size": _dir_size(DISK_0_SYSTEM)},
                {"id": "0.5", "name": "Загрузочный", "path": DISK_0_BOOT,
                 "size": _dir_size(DISK_0_BOOT)},
            ],
        })

    if os.path.isfile(DISK_1_VHD):
        info.append({
            "id": "1", "name": "ОСТАЛЬНОЕ", "type": "data",
            "vhd": DISK_1_VHD, "vhd_size": os.path.getsize(DISK_1_VHD),
            "data": DISK_1_VHD_DATA, "data_size": _dir_size(DISK_1_VHD_DATA),
            "size_gb": DISK_1_SIZE_GB, "icon": "💾", "sub": [],
        })

    return info


def format_info():
    lines = []
    info = partition_info()

    if not info:
        return "  (диски не созданы. Запусти: /disk init)"

    for p in info:
        lines.append(f"\n{p['icon']} Диск {p['id']}: {p['name']} (VHD)")
        lines.append(f"   Формат:       VHD динамический")
        lines.append(f"   VHD файл:     {p['vhd']}")
        lines.append(f"   Размер VHD:   {_human_size(p['vhd_size'])}")
        lines.append(f"   Данные:       {p['data']}")
        lines.append(f"   Занято:       {_human_size(p['data_size'])}")
        lines.append(f"   Макс. размер: {p['size_gb']} ГБ")

        if p["sub"]:
            for s in p["sub"]:
                lines.append(f"   ├─ {s['id']} {s['name']}")
                lines.append(f"   │  Занято: {_human_size(s['size'])}")

    return "\n".join(lines)


def _load_config():
    if os.path.isfile(VFS_CONFIG):
        try:
            with open(VFS_CONFIG, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": 1, "partitions": {}}


def _save_config(cfg):
    os.makedirs(VFS_ROOT, exist_ok=True)
    try:
        with open(VFS_CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def remove_partition_0(log=print):
    log("\n[DISK] Удаление Диска 0")
    for path in (DISK_0_VHD, DISK_0_VHD_DATA):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            log(f"[DISK]   🗑 {path}")
        elif os.path.isfile(path):
            try:
                os.remove(path)
                log(f"[DISK]   🗑 {path}")
            except Exception:
                pass
    cfg = _load_config()
    cfg.get("partitions", {}).pop("0", None)
    _save_config(cfg)


def remove_partition_1(log=print):
    log("\n[DISK] Удаление Диска 1")
    for path in (DISK_1_VHD, DISK_1_VHD_DATA):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            log(f"[DISK]   🗑 {path}")
        elif os.path.isfile(path):
            try:
                os.remove(path)
                log(f"[DISK]   🗑 {path}")
            except Exception:
                pass
    cfg = _load_config()
    cfg.get("partitions", {}).pop("1", None)
    _save_config(cfg)


def remove_all_partitions(log=print):
    remove_partition_0(log)
    remove_partition_1(log)
    _save_config({"version": 1, "partitions": {}})


def slash_disk(kernel, args):
    if not args:
        print("DreamUX VFS — управление дисками (VHD)")
        print()
        print("  /disk init             — создать диски (аккаунт + VHD)")
        print("  /disk 0 - 1 auto       — создать оба раздела")
        print("  /disk 0 auto           — только Диск 0")
        print("  /disk 1 auto           — только Диск 1")
        print("  /disk remove 0|1|all   — удалить")
        print("  /disks                 — список")
        print()
        return

    if args[0].lower() == "init":
        if is_initialized():
            r = input("⚠ Пересоздать? y/N: ")
            if r.lower() != "y":
                return
            shutil.rmtree(VFS_ROOT, ignore_errors=True)
        initialize_vfs()
        return

    if args[0].lower() == "remove":
        if len(args) < 2:
            print("[DISK] /disk remove 0|1|all")
            return
        t = args[1].lower()
        if t == "all":
            r = input("⚠ Удалить ВСЕ? y/N: ")
            if r.lower() == "y":
                remove_all_partitions()
        elif t == "0":
            r = input("⚠ Удалить Диск 0? y/N: ")
            if r.lower() == "y":
                remove_partition_0()
        elif t == "1":
            r = input("⚠ Удалить Диск 1? y/N: ")
            if r.lower() == "y":
                remove_partition_1()
        return

    full = " ".join(args).lower()
    if "auto" in full:
        parts = full.replace(":", " ").replace("-", " ").replace("auto", " ").split()
        create_0 = "0" in parts
        create_1 = "1" in parts

        os.makedirs(VFS_ROOT, exist_ok=True)
        if create_0:
            create_partition_0()
        if create_1:
            create_partition_1()

        cfg = _load_config()
        if "partitions" not in cfg:
            cfg["partitions"] = {}
        if create_0:
            cfg["partitions"]["0"] = {"name": "СИСТЕМА", "type": "system",
                                       "vhd": "vfs/disk0.vhd"}
        if create_1:
            cfg["partitions"]["1"] = {"name": "ОСТАЛЬНОЕ", "type": "data",
                                       "vhd": "vfs/disk1.vhd"}
        _save_config(cfg)
        return

    print(f"[DISK] Неизвестно: {args[0]}")


def slash_disks(kernel, args):
    if not args:
        print("DreamUX VFS — диски")
        print(format_info())
        print()
        print("  /disks              — список")
        print("  /disks mount 0|1    — открыть")
        print("  /disk init          — создать")
        print()
        return

    cmd = args[0].lower()

    if cmd == "mount" and len(args) > 1:
        p = get_partition_path(args[1])
        if p and os.path.isdir(p):
            try:
                if os.name == "nt":
                    os.startfile(p)
                else:
                    os.system(f'xdg-open "{p}"')
            except Exception as e:
                print(f"[DISK] {e}")
        return

    if cmd in ("help", "?"):
        slash_disks(kernel, [])
        return

    print(format_info())


def register(kernel):
    kernel.register_slash_command("disks", slash_disks, "DreamUX VFS — диски")
    kernel.register_slash_command("disk", slash_disk, "DreamUX VFS — управление")
    return []
