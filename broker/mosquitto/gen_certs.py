"""(Nâng cao) Tạo CA tự ký + chứng chỉ server cho MQTT TLS cổng 8883 (gọi lệnh openssl).

    python broker/mosquitto/gen_certs.py [CN]

Kết quả ở broker/mosquitto/certs/. Chép certs/ca.crt lên ESP32 (python -m mpremote fs cp ca.crt :ca.crt),
đặt MQTT_CA_FILE = "ca.crt" và MQTT_PORT = 8883 trong firmware/src/credentials.py.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

D = Path(__file__).resolve().parent / "certs"


def run(*args):
    subprocess.run(["openssl", *args], check=True)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cn = argv[0] if argv else "localhost"
    if not shutil.which("openssl"):
        raise SystemExit("Không tìm thấy openssl (Git for Windows có sẵn trong C:/Program Files/Git/usr/bin)")
    D.mkdir(exist_ok=True)
    run("req", "-x509", "-new", "-nodes", "-newkey", "rsa:2048", "-days", "3650", "-subj", "/CN=VKU-AIoT-CA",
        "-keyout", str(D / "ca.key"), "-out", str(D / "ca.crt"))
    run("req", "-new", "-nodes", "-newkey", "rsa:2048", "-subj", f"/CN={cn}", "-keyout", str(D / "server.key"),
        "-out", str(D / "server.csr"))
    (D / "ext.cnf").write_text(f"subjectAltName=DNS:{cn},DNS:localhost,IP:127.0.0.1\n", encoding="utf-8")
    run("x509", "-req", "-in", str(D / "server.csr"), "-CA", str(D / "ca.crt"), "-CAkey", str(D / "ca.key"),
        "-CAcreateserial", "-days", "825", "-extfile", str(D / "ext.cnf"), "-out", str(D / "server.crt"))
    print(f"Chứng chỉ ở {D} (CN={cn})")


if __name__ == "__main__":
    main()
