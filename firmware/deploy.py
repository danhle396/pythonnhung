from __future__ import annotations

USAGE = """Nạp firmware MicroPython lên ESP32 (chạy trên máy tính).

    python firmware/deploy.py                 # biên dịch .mpy + chép lên board (cổng tự dò) + khởi động lại
    python firmware/deploy.py --port COM5     # chỉ định cổng
    python firmware/deploy.py --source        # chép nguyên .py (dễ sửa bằng Thonny), không biên dịch
    python firmware/deploy.py --check         # chỉ biên dịch để kiểm tra cú pháp MicroPython
    python firmware/deploy.py --ota build/ota # tạo gói OTA (manifest.json + file) để phục vụ bằng http.server

Lần đầu với board mới: nạp MicroPython (ESP32_GENERIC) từ https://micropython.org/download/ESP32_GENERIC/
    python -m esptool --chip esp32 --port COM5 erase_flash
    python -m esptool --chip esp32 --port COM5 --baud 460800 write_flash 0x1000 ESP32_GENERIC-<phiên bản>.bin
rồi tạo firmware/src/credentials.py (WIFI_SSID, WIFI_PASS, MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS), chạy script này.
Xem log: python -m mpremote connect COM5 repl   (Ctrl-] để thoát)

Biên dịch sẵn .mpy giúp board không phải phân tích mã nguồn lúc chạy -> tiết kiệm RAM đáng kể.
main.py, boot.py, credentials.py luôn chép dạng .py.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
BUILD = HERE / "build"
KEEP_SOURCE = {"main.py", "boot.py", "credentials.py"}


def sources(ota=False):
    skip = {"credentials.py"} if ota else set()
    return sorted(p for p in SRC.glob("*.py") if p.name not in skip)


def compile_all(out: Path, as_source: bool, ota: bool = False) -> list[Path]:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = []
    for p in sources(ota):
        if as_source or p.name in KEEP_SOURCE:
            dst = out / p.name
            shutil.copy2(p, dst)
        else:
            dst = out / (p.stem + ".mpy")
            r = subprocess.run([sys.executable, "-m", "mpy_cross", "-march=xtensawin", "-o", str(dst), str(p)],
                               capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"Lỗi biên dịch {p.name}:\n{r.stderr or r.stdout}")
        files.append(dst)
    return files


def mpremote(port: str, *args: str):
    cmd = [sys.executable, "-m", "mpremote", "connect", port, *args]
    print("$", " ".join(cmd[2:]))
    subprocess.run(cmd, check=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="auto", help="cổng nối tiếp (COM5, /dev/ttyUSB0); mặc định tự dò")
    ap.add_argument("--source", action="store_true", help="chép .py thay vì .mpy")
    ap.add_argument("--check", action="store_true", help="chỉ biên dịch kiểm tra, không nạp")
    ap.add_argument("--ota", metavar="DIR", help="tạo gói OTA vào DIR thay vì nạp qua USB")
    a = ap.parse_args(argv)

    if not (SRC / "credentials.py").exists() and not a.check:
        print("! Chưa có firmware/src/credentials.py -> trạm chạy offline. Tạo file với WIFI_SSID, WIFI_PASS, MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS.")
    out = Path(a.ota) if a.ota else BUILD / "device"
    files = compile_all(out, a.source, bool(a.ota))
    print(f"Đã chuẩn bị {len(files)} file trong {out}")
    if a.check:
        return
    if a.ota:
        import config_reader
        ver = config_reader.fw_version()
        (out / "manifest.json").write_text(json.dumps({"version": ver, "files": [f.name for f in files]}, indent=1),
                                           encoding="utf-8")
        print(f"Gói OTA {ver}: python -m http.server 8080 -d {out}\n"
              f'rồi gửi lệnh {{"cmd":"ota","url":"http://<IP máy>:8080/manifest.json"}} từ dashboard/API.')
        return
    stale = [f.stem + (".py" if f.suffix == ".mpy" else ".mpy") for f in files if f.name not in KEEP_SOURCE]
    clean = "import os\nfor f in %r:\n try: os.remove(f)\n except OSError: pass\n" % stale
    mpremote(a.port, "exec", clean, "+", "fs", "cp", *[str(f) for f in files], ":", "+", "reset")
    print("Xong. Xem log: python -m mpremote connect", a.port, "repl")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    main()
