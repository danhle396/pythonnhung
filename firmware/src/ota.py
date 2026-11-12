# Cập nhật firmware qua mạng (OTA) cho MicroPython: tải các file .py/.mpy theo manifest rồi khởi động lại.
#   Lệnh: {"cmd":"ota","url":"http://<máy>:8080/manifest.json"}
#   Manifest (sinh bởi `python firmware/deploy.py --ota build/ota`):
#       {"version": "2.0.1", "files": ["alert.mpy", "edge_ai.mpy", "main.py", ...]}
#   Các file nằm cùng thư mục với manifest. Tải hết vào *.new trước, đủ mới đổi tên -> không bao giờ để board ở
#   trạng thái nửa cũ nửa mới. Chỉ hỗ trợ http:// (mạng nội bộ phòng thí nghiệm).
import json
import os
import socket


def _parse(url):
    if not url.startswith("http://"):
        raise ValueError("chi ho tro http://")
    rest = url[7:]
    host, _, path = rest.partition("/")
    port = 80
    if ":" in host:
        host, p = host.split(":", 1)
        port = int(p)
    return host, port, "/" + path


def http_get(url, dest=None, timeout_s=10, feed=None):
    """GET url. dest=None -> trả về bytes; dest=đường dẫn -> ghi file theo từng khối 1 kB."""
    host, port, path = _parse(url)
    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    s.settimeout(timeout_s)
    try:
        s.connect(addr)
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (path, host)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            c = s.recv(256)
            if not c:
                raise OSError("het du lieu")
            head += c
        head, _, body = head.partition(b"\r\n\r\n")
        code = int(head.split(b" ", 2)[1])
        if code != 200:
            raise OSError("HTTP %d" % code)
        out = open(dest, "wb") if dest else None
        chunks = []
        try:
            while True:
                if out:
                    out.write(body)
                else:
                    chunks.append(body)
                if feed:
                    feed()
                body = s.recv(1024)
                if not body:
                    break
        finally:
            if out:
                out.close()
        return None if dest else b"".join(chunks)
    finally:
        s.close()


def update(manifest_url, feed=None, base=""):
    """Tải và cài bản cập nhật. Trả về (True, phiên bản) hoặc ném lỗi; caller tự khởi động lại."""
    man = json.loads(http_get(manifest_url, feed=feed))
    files = man["files"]
    root = manifest_url.rsplit("/", 1)[0]
    for name in files:
        if "/" in name or name.startswith("."):
            raise ValueError("ten file khong hop le: " + name)
    done = []
    try:
        for name in files:
            http_get(root + "/" + name, base + "/" + name + ".new", feed=feed)
            done.append(name)
    except Exception:
        for name in done:
            try:
                os.remove(base + "/" + name + ".new")
            except OSError:
                pass
        raise
    for name in files:
        # .py và .mpy cùng tên: bỏ bản còn lại để MicroPython nạp đúng file mới
        stem = name.rsplit(".", 1)[0]
        for other in (stem + ".py", stem + ".mpy"):
            if other != name and other not in ("main.py", "boot.py"):
                try:
                    os.remove(base + "/" + other)
                except OSError:
                    pass
        try:
            os.remove(base + "/" + name)
        except OSError:
            pass
        os.rename(base + "/" + name + ".new", base + "/" + name)
    return True, str(man.get("version", "?"))
