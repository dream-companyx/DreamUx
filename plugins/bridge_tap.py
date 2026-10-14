"""
DreamUX Bridge TAP — работа с TAP-Windows адаптером.
Даёт DreamUX свой MAC-адрес и сетевой интерфейс.

Установка TAP:
    1. Скачай tap-windows-9.24.7-I601-Win10.exe
       https://build.openvpn.net/downloads/releases/
    2. Установи
    3. Запусти setup_tap.bat от админа (создаст DreamUX-NIC)

Slash-команды:
    /bridge status   — состояние
    /bridge setup    — создать TAP + MAC
    /bridge open     — открыть TAP
    /bridge close    — закрыть TAP
    /bridge mac      — MAC-адрес
    /bridge test     — послать ARP
"""

import os
import sys
import time
import json
import struct
import socket
import threading
import subprocess
import ctypes
from ctypes import wintypes


TAP_NAME = "DreamUX-NIC"
TAP_MAC = "00-1A-2B-3C-4D-5E"
TAP_IP = "192.168.100.2"
TAP_MASK = "255.255.255.0"


# ============================================================
# PowerShell
# ============================================================
def _run_ps(command, timeout=30):
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return r.stdout.strip(), r.returncode
    except Exception as e:
        return f"error: {e}", -1


def get_tap_mac():
    out, _ = _run_ps(
        f"Get-NetAdapter -Name '{TAP_NAME}' -ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty MacAddress"
    )
    return out.strip() if out else ""


def get_tap_ip():
    out, _ = _run_ps(
        f"Get-NetIPAddress -InterfaceAlias '{TAP_NAME}' -AddressFamily IPv4 "
        f"-ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty IPAddress"
    )
    return out.strip() if out else ""


def get_tap_status():
    out, _ = _run_ps(
        f"Get-NetAdapter -Name '{TAP_NAME}' -ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty Status"
    )
    return out.strip() if out else ""


def get_tap_guid():
    out, _ = _run_ps(
        f"Get-NetAdapter -Name '{TAP_NAME}' -ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty InterfaceGuid"
    )
    return out.strip() if out else ""


# ============================================================
# WinAPI: открытие TAP
# ============================================================
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

TAP_IOCTL_GET_MAC = 0x90002004
TAP_IOCTL_GET_VERSION = 0x90002008
TAP_IOCTL_SET_MEDIA_STATUS = 0x9000200C
TAP_IOCTL_CONFIG_TUN = 0x90002010


class TAPDevice:
    """Обёртка над TAP-Windows устройством."""

    def __init__(self, adapter_name=TAP_NAME):
        self.adapter_name = adapter_name
        self.handle = None
        self.running = False
        self._thread = None
        self._on_packet = None

    def open(self):
        guid = get_tap_guid()
        if not guid:
            raise RuntimeError(f"Адаптер '{self.adapter_name}' не найден")

        tap_path = f"\\\\.\\Global\\{{{guid}}}.tap"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        handle = kernel32.CreateFileW(
            tap_path,
            GENERIC_READ | GENERIC_WRITE,
            0, None, OPEN_EXISTING,
            0x40000000,  # FILE_FLAG_OVERLAPPED
            None,
        )

        if handle == INVALID_HANDLE_VALUE or handle == 0xFFFFFFFFFFFFFFFF:
            err = ctypes.get_last_error()
            raise RuntimeError(f"CreateFileW failed: error {err}")

        self.handle = handle
        self._set_media_status(True)
        self._config_tun()
        return True

    def _set_media_status(self, connected=True):
        if not self.handle:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        in_buf = struct.pack("<I", 1 if connected else 0)
        bytes_returned = wintypes.DWORD(0)
        kernel32.DeviceIoControl(
            self.handle, TAP_IOCTL_SET_MEDIA_STATUS,
            in_buf, len(in_buf), None, 0,
            ctypes.byref(bytes_returned), None,
        )

    def _config_tun(self):
        if not self.handle:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        try:
            local_ip = struct.unpack(">I", socket.inet_aton(TAP_IP))[0]
            remote_net = struct.unpack(">I", socket.inet_aton("192.168.100.0"))[0]
            mask = struct.unpack(">I", socket.inet_aton(TAP_MASK))[0]
            in_buf = struct.pack("<III", local_ip, remote_net, mask)
            bytes_returned = wintypes.DWORD(0)
            kernel32.DeviceIoControl(
                self.handle, TAP_IOCTL_CONFIG_TUN,
                in_buf, len(in_buf), None, 0,
                ctypes.byref(bytes_returned), None,
            )
        except Exception:
            pass

    def get_mac(self):
        if not self.handle:
            return None
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        out_buf = ctypes.create_string_buffer(6)
        bytes_returned = wintypes.DWORD(0)
        ok = kernel32.DeviceIoControl(
            self.handle, TAP_IOCTL_GET_MAC,
            None, 0, out_buf, 6,
            ctypes.byref(bytes_returned), None,
        )
        if ok:
            mac = out_buf.raw[:6]
            return ":".join(f"{b:02X}" for b in mac)
        return None

    def close(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self.handle:
            try:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None

    def start_reading(self, on_packet):
        self._on_packet = on_packet
        self.running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        buf_size = 65536
        buf = ctypes.create_string_buffer(buf_size)
        while self.running:
            try:
                bytes_read = wintypes.DWORD(0)
                ok = kernel32.ReadFile(
                    self.handle, buf, buf_size,
                    ctypes.byref(bytes_read), None,
                )
                if not ok:
                    time.sleep(0.01)
                    continue
                if bytes_read.value > 0:
                    data = buf.raw[:bytes_read.value]
                    if self._on_packet:
                        try:
                            self._on_packet(data)
                        except Exception as e:
                            print(f"[TAP] on_packet: {e}")
            except Exception as e:
                if self.running:
                    print(f"[TAP] read: {e}")
                time.sleep(0.1)

    def write_packet(self, data):
        if not self.handle:
            return False
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        bytes_written = wintypes.DWORD(0)
        ok = kernel32.WriteFile(
            self.handle, data, len(data),
            ctypes.byref(bytes_written), None,
        )
        return bool(ok)


_TAP = None


def get_tap():
    global _TAP
    if _TAP is None:
        _TAP = TAPDevice(TAP_NAME)
    return _TAP


def open_tap():
    tap = get_tap()
    if tap.handle:
        return True
    try:
        tap.open()
        return True
    except Exception as e:
        print(f"[TAP] Ошибка открытия: {e}")
        return False


def close_tap():
    global _TAP
    if _TAP:
        _TAP.close()
        _TAP = None


# ============================================================
# Setup TAP
# ============================================================
def ensure_tap_adapter(log=print):
    """Создаёт TAP-адаптер с нужным MAC, если его нет."""
    out, _ = _run_ps(
        f"Get-NetAdapter -Name '{TAP_NAME}' -ErrorAction SilentlyContinue | "
        f"Select-Object -ExpandProperty Name"
    )
    if TAP_NAME in out:
        log(f"[BRIDGE] TAP '{TAP_NAME}' уже существует")
        return True

    addtap = None
    for p in (
        r"C:\Program Files\TAP-Windows\bin\addtap.bat",
        r"C:\Program Files (x86)\TAP-Windows\bin\addtap.bat",
        r"C:\Program Files\OpenVPN\bin\addtap.bat",
        r"C:\Program Files\OpenVPN\bin\addtap.bat",
    ):
        if os.path.isfile(p):
            addtap = p
            break

    if not addtap:
        log("[BRIDGE] ⛔ addtap.bat не найден")
        log("[BRIDGE] Установи TAP-Windows:")
        log("[BRIDGE]   https://build.openvpn.net/downloads/releases/")
        return False

    log(f"[BRIDGE] Создаю TAP через {addtap}")
    try:
        subprocess.run([addtap], shell=True,
                       creationflags=subprocess.CREATE_NO_WINDOW,
                       timeout=60)
    except Exception as e:
        log(f"[BRIDGE] ⛔ addtap: {e}")
        return False

    time.sleep(3)

    # Переименовываем
    _run_ps(
        f"$new = Get-NetAdapter | Where-Object {{ "
        f"$_.InterfaceDescription -like '*TAP*' -and $_.Name -ne '{TAP_NAME}' }} "
        f"| Select-Object -First 1; "
        f"if ($new) {{ Rename-NetAdapter -Name $new.Name -NewName '{TAP_NAME}' "
        f"-ErrorAction SilentlyContinue }}"
    )

    # MAC
    _run_ps(f"Set-NetAdapter -Name '{TAP_NAME}' -MacAddress '{TAP_MAC}' "
            f"-Confirm:$false")

    # Включаем
    _run_ps(f"Enable-NetAdapter -Name '{TAP_NAME}' -Confirm:$false")

    time.sleep(2)

    # IP
    _run_ps(
        f"Remove-NetIPAddress -InterfaceAlias '{TAP_NAME}' -Confirm:$false "
        f"-ErrorAction SilentlyContinue; "
        f"New-NetIPAddress -InterfaceAlias '{TAP_NAME}' "
        f"-IPAddress '{TAP_IP}' -PrefixLength 24 -ErrorAction SilentlyContinue"
    )

    log(f"[BRIDGE] ✅ TAP готов: {TAP_NAME}")
    return True


def status():
    return {
        "name": TAP_NAME,
        "exists": bool(get_tap_guid()),
        "mac": get_tap_mac(),
        "ip": get_tap_ip(),
        "status": get_tap_status(),
        "opened": _TAP is not None and _TAP.handle is not None,
    }


def format_status():
    st = status()
    lines = []
    lines.append("🌐 DreamUX TAP Bridge")
    lines.append(f"   Адаптер:   {st['name']}")
    lines.append(f"   Существует: {'✅' if st['exists'] else '❌'}")
    lines.append(f"   MAC:       {st['mac'] or '—'}")
    lines.append(f"   IP:        {st['ip'] or '—'}")
    lines.append(f"   Статус:    {st['status'] or '—'}")
    lines.append(f"   Открыт:    {'✅' if st['opened'] else '❌'}")
    return "\n".join(lines)


# ============================================================
# Slash-команды
# ============================================================
def slash_bridge(kernel, args):
    if not args:
        print("DreamUX Bridge TAP")
        print("  /bridge status   — состояние")
        print("  /bridge setup    — создать TAP + MAC")
        print("  /bridge open     — открыть TAP")
        print("  /bridge close    — закрыть TAP")
        print("  /bridge mac      — MAC-адрес")
        print("  /bridge test     — послать ARP")
        return

    cmd = args[0].lower()

    if cmd == "status":
        print(format_status())
        return

    if cmd == "setup":
        ensure_tap_adapter()
        print(format_status())
        return

    if cmd == "open":
        if open_tap():
            print("[TAP] ✅ TAP открыт")
            print(format_status())
        else:
            print("[TAP] ⛔ Не удалось открыть")
        return

    if cmd == "close":
        close_tap()
        print("[TAP] TAP закрыт")
        return

    if cmd == "mac":
        print(f"MAC (Windows): {get_tap_mac()}")
        tap = get_tap()
        if tap.handle:
            print(f"MAC (TAP API): {tap.get_mac()}")
        return

    if cmd == "test":
        tap = get_tap()
        if not tap.handle:
            print("[TAP] Сначала /bridge open")
            return
        arp = bytes.fromhex(
            "ffffffffffff"
            "001a2b3c4d5e"
            "0806"
            "0001"
            "0800"
            "06"
            "04"
            "0001"
            "001a2b3c4d5e"
            "c0a86402"
            "000000000000"
            "c0a86401"
        )
        ok = tap.write_packet(arp)
        print(f"[TAP] ARP отправлен: {'✅' if ok else '❌'}")
        return

    print(f"[TAP] Неизвестно: {cmd}")


def register(kernel):
    kernel.register_slash_command(
        "bridge", slash_bridge,
        "DreamUX Bridge TAP — сеть со своим MAC",
    )
    return []
