"""
DreamUX Paket Installer — установщик пакетов и архивов.
Работает с .dupfi (манифест) и .duap/.zip (архивы).
Устанавливает в DRXFS disk2:/apps/<name>/.

Slash-команды:
    /dupfi install <файл|url>   — установить пакет
    /dupfi remove <имя>         — удалить
    /dupfi list                 — список
    /dupfi info <файл>          — манифест
    /dupfi whoami               — права
    /duap create <zip> [<duap>] — создать .duap
    /duap verify <duap>         — проверить SHA256
    /duap info <duap>           — манифест архива
    /duap extract <duap> <файл> — извлечь файл
"""

import os
import io
import json
import shutil
import zipfile
import urllib.request
import urllib.error
import datetime
import tempfile

from plugins.base import Interface

try:
    from plugins import access
    HAS_ACCESS = True
except ImportError:
    access = None
    HAS_ACCESS = False

try:
    from plugins import duap as _duap
    HAS_DUAP = True
except ImportError:
    _duap = None
    HAS_DUAP = False

try:
    from plugins import vfs as _vfs
    HAS_VFS = True
except ImportError:
    _vfs = None
    HAS_VFS = False


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)

PACKAGES_DIR = os.path.join(KERNEL_DIR, "packages")
DOWNLOADS_DIR = os.path.join(KERNEL_DIR, "downloads")


def _ensure_dirs():
    for d in (PACKAGES_DIR, DOWNLOADS_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


_ensure_dirs()


def _check(perm, log=print):
    if not HAS_ACCESS:
        return True
    s = access.get_session()
    if s.can(perm):
        return True
    log(f"[DUPFI] ⛔ Доступ запрещён: {perm} "
        f"(уровень {s.level} {s.level_name()})")
    return False


def _ts():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _human_size(n):
    for u in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} ПБ"


def _download(url, dst, log=print):
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        log(f"[DUPFI] Скачиваю: {url}")
        req = urllib.request.Request(
            url, headers={"User-Agent": "DreamUX-DUPFI/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(dst, "wb") as f:
            f.write(data)
        log(f"[DUPFI] ✅ {os.path.basename(dst)} ({_human_size(len(data))})")
        return True
    except urllib.error.HTTPError as e:
        log(f"[DUPFI] ⛔ HTTP {e.code}: {url}")
        return False
    except Exception as e:
        log(f"[DUPFI] ⛔ {e}")
        return False


def _detect_archive(path):
    if HAS_DUAP:
        return _duap.detect_format(path)
    if zipfile.is_zipfile(path):
        return "zip"
    try:
        with open(path, "rb") as f:
            if f.read(4) == b"DUAP":
                return "duap"
    except Exception:
        pass
    return None


def _open_archive(path):
    fmt = _detect_archive(path)
    if fmt == "duap":
        if HAS_DUAP:
            ok, msg = _duap.verify_duap(path)
            if not ok:
                raise ValueError(f"DUAP повреждён: {msg}")
            return _duap.open_duap(path)
        with open(path, "rb") as f:
            f.seek(64)
            return zipfile.ZipFile(io.BytesIO(f.read()), "r")
    elif fmt == "zip":
        return zipfile.ZipFile(path, "r")
    raise ValueError("Не .zip и не .duap")


def _parse_dupfi(path):
    if not os.path.isfile(path):
        return None, "файл не найден"

    data = {
        "name": "Без имени",
        "version": "0.0.0",
        "author": "Неизвестен",
        "description": "",
        "git": "",
        "files": [],
        "level": 2,
    }

    section = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("[") and s.endswith("]"):
                    section = s[1:-1].strip().lower()
                    continue
                if section == "filegit":
                    data["files"].append(s)
                    continue
                if "=" in s:
                    k, _, v = s.partition("=")
                    k = k.strip().lower()
                    v = v.strip()
                    if section == "git" and k == "url":
                        data["git"] = v
                    elif section in (None, "main"):
                        if k == "name":
                            data["name"] = v
                        elif k == "version":
                            data["version"] = v
                        elif k == "author":
                            data["author"] = v
                        elif k == "description":
                            data["description"] = v
                        elif k == "git":
                            data["git"] = v
                        elif k == "level":
                            try:
                                data["level"] = int(v)
                            except ValueError:
                                pass
    except Exception as e:
        return None, f"ошибка: {e}"

    if not data["git"]:
        return None, "не указан Git url"
    if not data["files"]:
        return None, "не указан FileGit список"

    return data, None


INSTALLED_FILE = os.path.join(KERNEL_DIR, "installed_packages.json")


def _load_installed():
    if os.path.isfile(INSTALLED_FILE):
        try:
            with open(INSTALLED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_installed(data):
    try:
        with open(INSTALLED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[DUPFI] Ошибка реестра: {e}")


def _install(dupfi_path, log=print):
    if not _check("install_dupi", log):
        return False

    if not HAS_VFS:
        log("[DUPFI] ⛔ VFS недоступен — установка невозможна")
        return False

    data, err = _parse_dupfi(dupfi_path)
    if err:
        log(f"[DUPFI] ⛔ {err}")
        return False

    name = data["name"]
    version = data["version"]
    author = data["author"]
    git_url = data["git"]
    files = data["files"]
    pkg_level = data.get("level", 2)

    if HAS_ACCESS:
        s = access.get_session()
        if s.level > pkg_level:
            log(f"[DUPFI] ⛔ Недостаточно прав: пакет требует уровень {pkg_level}")
            return False

    log(f"\n[DUPFI] Установка: {name} v{version}")
    log(f"[DUPFI] Автор:    {author}")
    log(f"[DUPFI] Уровень:  {pkg_level}")
    log(f"[DUPFI] Источник: {git_url}")
    log(f"[DUPFI] Файлы ({len(files)}):")
    for f in files:
        log(f"[DUPFI]   • {f}")

    tmp_dir = tempfile.mkdtemp(prefix="dupfi_")
    archive_name = os.path.basename(git_url.split("?")[0]) or "archive.zip"
    if not archive_name.endswith((".zip", ".duap")):
        archive_name += ".zip"
    archive_path = os.path.join(tmp_dir, archive_name)

    if not _download(git_url, archive_path, log=log):
        return False

    fmt = _detect_archive(archive_path)
    if fmt is None:
        log("[DUPFI] ⛔ Не .zip и не .duap")
        return False
    log(f"[DUPFI] Формат: {fmt.upper()}")

    if fmt == "duap" and HAS_DUAP:
        ok, msg = _duap.verify_duap(archive_path)
        if not ok:
            log(f"[DUPFI] ⛔ {msg}")
            return False
        log(f"[DUPFI] ✅ SHA256 OK")

    # Создаём папку в DRXFS
    try:
        _vfs.mkdir("disk2", f"apps/{name}")
    except Exception as e:
        log(f"[DUPFI] ⚠ mkdir apps/{name}: {e}")

    extracted = 0
    try:
        with _open_archive(archive_path) as zf:
            names = zf.namelist()
            log(f"[DUPFI] В архиве: {len(names)} файлов")

            for wanted in files:
                matches = [n for n in names
                           if n.endswith(wanted) or n == wanted]
                if not matches:
                    log(f"[DUPFI] ⚠ Не найден: {wanted}")
                    continue
                for match in matches:
                    try:
                        data_bytes = zf.read(match)
                        inner_path = f"apps/{name}/{wanted}"
                        if _vfs.write("disk2", inner_path, data_bytes):
                            log(f"[DUPFI] ✅ {wanted}")
                            extracted += 1
                        else:
                            log(f"[DUPFI] ⛔ write fail: {wanted}")
                    except Exception as e:
                        log(f"[DUPFI] ⛔ {wanted}: {e}")
    except Exception as e:
        log(f"[DUPFI] ⛔ Ошибка распаковки: {e}")
        return False

    # Копируем .dupfi манифест в DRXFS
    try:
        with open(dupfi_path, "rb") as f:
            _vfs.write("disk2", f"apps/{name}/{name}.dupfi", f.read())
        log(f"[DUPFI] ✅ {name}.dupfi → apps/{name}/")
    except Exception:
        pass

    # Запись в реестр (в DRXFS + локально)
    installed_by = "unknown"
    if HAS_ACCESS:
        installed_by = access.get_session().username

    entry = {
        "version": version,
        "author": author,
        "git": git_url,
        "archive_format": fmt,
        "level": pkg_level,
        "files": files,
        "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "installed_by": installed_by,
        "extracted": extracted,
    }

    # Реестр в DRXFS
    try:
        reg_raw = _vfs.read("disk0", "system/installed.json")
        registry = {}
        if reg_raw:
            try:
                registry = json.loads(reg_raw.decode("utf-8"))
            except Exception:
                registry = {}
        registry[name] = entry
        _vfs.write("disk0", "system/installed.json",
                   json.dumps(registry, indent=2, ensure_ascii=False))
    except Exception as e:
        log(f"[DUPFI] ⚠ реестр DRXFS: {e}")

    # Реестр локальный (для обратной совместимости)
    installed = _load_installed()
    installed[name] = entry
    _save_installed(installed)

    # Чистка временного архива
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    log(f"\n[DUPFI] ✅ Установлено: {name} v{version}")
    log(f"[DUPFI] 📁 disk2:/apps/{name}/")
    log(f"[DUPFI] 📦 Извлечено: {extracted}/{len(files)}")
    return True


def _remove(name, log=print):
    if not _check("remove_package", log):
        return

    if not HAS_VFS:
        log("[DUPFI] ⛔ VFS недоступен")
        return

    installed = _load_installed()
    if name not in installed:
        log(f"[DUPFI] ⛔ Не найден: {name}")
        return

    if HAS_ACCESS:
        s = access.get_session()
        pkg_level = installed[name].get("level", 2)
        if s.level > 1 and pkg_level < 2:
            log(f"[DUPFI] ⛔ Нельзя удалить системный пакет")
            return

    # Удаление из DRXFS
    try:
        _vfs.delete("disk2", f"apps/{name}")
        log(f"[DUPFI] 🗑 Удалено из disk2:/apps/{name}")
    except Exception as e:
        log(f"[DUPFI] ⚠ DRXFS delete: {e}")

    # Удаление из реестра DRXFS
    try:
        reg_raw = _vfs.read("disk0", "system/installed.json")
        if reg_raw:
            registry = json.loads(reg_raw.decode("utf-8"))
            if name in registry:
                del registry[name]
                _vfs.write("disk0", "system/installed.json",
                           json.dumps(registry, indent=2, ensure_ascii=False))
    except Exception:
        pass

    # Удаление из локального реестра
    del installed[name]
    _save_installed(installed)

    log(f"[DUPFI] ✅ Удалено: {name}")


def _list_installed(log=print):
    if not _check("view_installed", log):
        return

    installed = _load_installed()
    if not installed:
        # Пробуем через VFS
        if HAS_VFS:
            try:
                items = _vfs.list_dir("disk2", "apps")
                dirs = [n for k, n, s in items if k == "dir"]
                if dirs:
                    log(f"\n[DUPFI] Приложения в disk2:/apps/ ({len(dirs)}):")
                    for name in sorted(dirs):
                        log(f"  • {name}")
                    log("")
                    return
            except Exception:
                pass
        log("[DUPFI] Пакетов нет.")
        return

    log(f"\n[DUPFI] Установленные пакеты ({len(installed)}):\n")
    log(f"  {'Имя':<20} {'Вер':<8} {'Ур':<4} {'Формат':<6} {'Автор':<18}")
    log("  " + "-" * 70)
    for name, info in sorted(installed.items()):
        log(f"  {name:<20} {info.get('version','—'):<8} "
            f"{info.get('level','—'):<4} "
            f"{info.get('archive_format','—'):<6} "
            f"{info.get('author','—'):<18}")
    log("")


def _show_info(path, log=print):
    data, err = _parse_dupfi(path)
    if err:
        log(f"[DUPFI] ⛔ {err}")
        return
    log(f"\n[DUPFI] Информация:")
    log(f"  Имя:      {data['name']}")
    log(f"  Версия:   {data['version']}")
    log(f"  Автор:    {data['author']}")
    log(f"  Описание: {data['description']}")
    log(f"  Уровень:  {data.get('level', 2)}")
    log(f"  Git:      {data['git']}")
    log(f"  Файлы ({len(data['files'])}):")
    for f in data["files"]:
        log(f"    • {f}")
    log("")


def slash_dupfi(kernel, args):
    if not args:
        s_info = ""
        if HAS_ACCESS:
            s = access.get_session()
            s_info = f"Сессия: {s.username} (L{s.level} {s.level_name()})\n"
        print("DreamUX Paket Installer (DRXFS)")
        print(s_info)
        print("  /dupfi install <файл|url>   — установить")
        print("  /dupfi remove <имя>         — удалить")
        print("  /dupfi list                 — список")
        print("  /dupfi info <файл>          — манифест")
        print("  /dupfi whoami               — права")
        print()
        print("Установка: disk2:/apps/<name>/")
        print("Архивы: .zip, .duap")
        print()
        return

    cmd = args[0].lower()
    rest = args[1:]

    if cmd == "install":
        if not rest:
            print("[DUPFI] Укажите файл или URL.")
            return
        src = rest[0]

        if src.startswith(("http://", "https://")):
            fname = os.path.basename(src.split("?")[0])
            dst = os.path.join(PACKAGES_DIR, fname)
            if not _download(src, dst):
                return
            src = dst

        if not os.path.isfile(src):
            alt = os.path.join(PACKAGES_DIR, src)
            if os.path.isfile(alt):
                src = alt
            else:
                print(f"[DUPFI] ⛔ Не найден: {src}")
                return

        if not src.endswith(".dupfi"):
            print(f"[DUPFI] ⛔ Не .dupfi: {os.path.basename(src)}")
            return

        _install(src)

    elif cmd == "remove":
        if rest:
            _remove(rest[0])
        else:
            print("[DUPFI] Укажите имя.")

    elif cmd == "list":
        _list_installed()

    elif cmd == "info":
        if rest:
            _show_info(rest[0])
        else:
            print("[DUPFI] Укажите файл.")

    elif cmd == "whoami":
        if HAS_ACCESS:
            s = access.get_session()
            print(f"Пользователь: {s.username}")
            print(f"Уровень:      {s.level} ({s.level_name()})")
            print(f"Права:")
            for p, lv in access.PERMISSIONS.items():
                m = "✅" if s.level in lv else "⛔"
                print(f"  {m}  {p}")

    elif cmd in ("help", "?"):
        slash_dupfi(kernel, [])

    else:
        print(f"[DUPFI] ⛔ Неизвестная команда: {cmd}")


def slash_duap(kernel, args):
    if not HAS_DUAP:
        print("[DUAP] ⛔ Модуль duap.py не загружен")
        return

    if not args:
        print("DreamUX Archive Paket (.duap)")
        print()
        print("  /duap create <zip> [<duap>]  — создать .duap")
        print("  /duap verify <duap>          — проверить SHA256")
        print("  /duap info <duap>            — манифест")
        print("  /duap extract <duap> <файл>  — извлечь файл")
        print()
        return

    cmd = args[0].lower()
    rest = args[1:]

    if cmd == "create":
        if not _check("duap_create"):
            return
        if not rest:
            print("[DUAP] Укажите .zip файл")
            return
        zip_path = rest[0]
        if not os.path.isfile(zip_path):
            alt = os.path.join(PACKAGES_DIR, zip_path)
            if os.path.isfile(alt):
                zip_path = alt
            else:
                print(f"[DUAP] ⛔ Не найден: {zip_path}")
                return
        duap_path = rest[1] if len(rest) > 1 else zip_path.replace(".zip", ".duap")
        _duap.create_duap(zip_path, duap_path)

    elif cmd == "verify":
        if not _check("duap_verify"):
            return
        if not rest:
            print("[DUAP] Укажите .duap")
            return
        p = rest[0]
        if not os.path.isfile(p):
            alt = os.path.join(PACKAGES_DIR, p)
            if os.path.isfile(alt):
                p = alt
        ok, msg = _duap.verify_duap(p)
        print(f"[DUAP] {'✅' if ok else '⛔'} {msg}")

    elif cmd == "info":
        if not rest:
            print("[DUAP] Укажите .duap")
            return
        p = rest[0]
        if not os.path.isfile(p):
            alt = os.path.join(PACKAGES_DIR, p)
            if os.path.isfile(alt):
                p = alt
        if not _duap.is_duap(p):
            print("[DUAP] ⛔ Не .duap файл")
            return
        hdr = _duap.read_duap_header(p)
        mf = _duap.read_manifest(p)
        print(f"\n[DUAP] Версия:  {hdr['version']}")
        print(f"[DUAP] SHA256:  {hdr['sha256'][:32]}...")
        print(f"[DUAP] Создан:  {mf.get('created_at', '?')}")
        print(f"[DUAP] Файлов:  {len(mf.get('files', []))}")
        for f in mf.get("files", []):
            print(f"  • {f['name']}  ({f['size']} байт)")
        print()

    elif cmd == "extract":
        if not _check("duap_extract"):
            return
        if len(rest) < 2:
            print("[DUAP] /duap extract <duap> <файл>")
            return
        p, wanted = rest[0], rest[1]
        if not os.path.isfile(p):
            alt = os.path.join(PACKAGES_DIR, p)
            if os.path.isfile(alt):
                p = alt
        try:
            with _duap.open_archive(p) as zf:
                matches = [n for n in zf.namelist()
                           if n.endswith(wanted) or n == wanted]
                if not matches:
                    print(f"[DUAP] ⛔ Не найден: {wanted}")
                    return
                out = os.path.join(PACKAGES_DIR, os.path.basename(matches[0]))
                with zf.open(matches[0]) as src:
                    with open(out, "wb") as dst:
                        dst.write(src.read())
                print(f"[DUAP] ✅ Извлечено: {out}")
        except Exception as e:
            print(f"[DUAP] ⛔ {e}")

    elif cmd in ("help", "?"):
        slash_duap(kernel, [])

    else:
        print(f"[DUAP] ⛔ Неизвестная команда: {cmd}")


def register(kernel):
    kernel.register_slash_command(
        "dupfi", slash_dupfi,
        "DreamUX Paket Installer — .dupfi/.duap/.zip → DRXFS",
    )
    kernel.register_slash_command(
        "duap", slash_duap,
        "DreamUX Archive Paket — работа с .duap",
    )
    return []
