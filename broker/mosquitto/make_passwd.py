from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIN_DEFAULT = Path("C:/Program Files/mosquitto/mosquitto_passwd.exe")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out = Path(argv[0]) if argv else HERE / "passwd"
    exe = shutil.which("mosquitto_passwd") or (str(WIN_DEFAULT) if WIN_DEFAULT.exists() else None)
    if not exe:
        raise SystemExit("Không tìm thấy mosquitto_passwd — cài Mosquitto hoặc thêm vào PATH")
    users = [("backend", os.environ.get("MQTT_BACKEND_PASS", "backend-pass")),
             ("dashboard", os.environ.get("MQTT_DASHBOARD_PASS", "dashboard-pass"))]
    for dev in os.environ.get("MQTT_DEVICES", "station01 station02 station03").split():
        users.append((dev, os.environ.get("MQTT_DEVICE_PASS", "change-me")))
    out.write_text("", encoding="utf-8")
    for user, pw in users:
        subprocess.run([exe, "-b", str(out), user, pw], check=True)
    try:
        os.chmod(out, 0o700)
    except OSError:
        pass
    print(f"Đã tạo {out} ({len(users)} tài khoản)")


if __name__ == "__main__":
    main()
