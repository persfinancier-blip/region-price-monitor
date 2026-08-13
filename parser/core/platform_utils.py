# -*- coding: utf-8 -*-
"""Кросс-платформенные утилиты (Windows + Linux)."""
import platform
import subprocess


def kill_browser():
    """Снимаем висящие процессы браузера, чтобы профиль не был залочен."""
    sysname = platform.system()
    if sysname == "Windows":
        for img in ("chrome.exe", "chromedriver.exe"):
            try:
                subprocess.run(["taskkill", "/F", "/IM", img], capture_output=True, timeout=10)
            except Exception:
                pass
    else:
        for name in ("chrome", "chromedriver", "chromium"):
            try:
                subprocess.run(["pkill", "-f", name], capture_output=True, timeout=10)
            except Exception:
                pass


def kill_pid_tree(pid):
    """Гарантированно закрываем окно браузера по PID (uc.Chrome иногда не закрывается)."""
    if not pid:
        return
    if platform.system() == "Windows":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=10)
        except Exception:
            pass
    else:
        try:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True, timeout=10)
        except Exception:
            pass


def get_chrome_major_version():
    """Мажорная версия Chrome из реестра (Win) / CLI (Linux/Mac)."""
    sysname = platform.system()
    try:
        if sysname == "Windows":
            import winreg
            for hive_name, path in [
                ("HKEY_CURRENT_USER", r"Software\Google\Chrome\BLBeacon"),
                ("HKEY_LOCAL_MACHINE", r"Software\Google\Chrome\BLBeacon"),
                ("HKEY_LOCAL_MACHINE", r"Software\WOW6432Node\Google\Chrome\BLBeacon"),
            ]:
                try:
                    with winreg.OpenKey(getattr(winreg, hive_name), path) as key:
                        version, _ = winreg.QueryValueEx(key, "version")
                        return int(version.split(".")[0])
                except FileNotFoundError:
                    continue
        elif sysname == "Darwin":
            r = subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
                               capture_output=True, text=True, timeout=5)
            return int(r.stdout.strip().split()[2].split(".")[0])
        else:
            for cmd in ["google-chrome", "chromium-browser", "chromium", "chrome"]:
                try:
                    r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
                    return int(r.stdout.strip().split()[2].split(".")[0])
                except Exception:
                    continue
    except Exception:
        pass
    return None
