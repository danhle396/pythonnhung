from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

BROWSERS = [
    os.environ.get("BROWSER_EXE", ""),
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_browser() -> str:
    for p in BROWSERS:
        if p and Path(p).exists():
            return p
    raise FileNotFoundError("Không tìm thấy Edge/Chrome — đặt biến môi trường BROWSER_EXE")


class Browser:
    def __init__(self, width=1800, height=1200, scale=2, exe=None):
        self.exe = exe or find_browser()
        self.width, self.height, self.scale = width, height, scale
        self._id = 0

    def __enter__(self):
        self.profile = tempfile.mkdtemp(prefix="cdp-")
        self.proc = subprocess.Popen(
            [self.exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             "--remote-debugging-port=0", f"--user-data-dir={self.profile}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.profile) / "DevToolsActivePort"
        for _ in range(200):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.05)
        port = int(port_file.read_text().split()[0])
        targets = []
        for _ in range(100):
            targets = [t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
                       if t.get("type") == "page"]
            if targets:
                break
            time.sleep(0.05)
        self.ws = connect(targets[0]["webSocketDebuggerUrl"], max_size=None, open_timeout=20)
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Emulation.setDeviceMetricsOverride", width=self.width, height=self.height,
                  deviceScaleFactor=self.scale, mobile=False)
        return self

    def __exit__(self, *exc):
        try:
            self.ws.close()
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            shutil.rmtree(self.profile, ignore_errors=True)

    def call(self, method, timeout=60, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.ws.recv(timeout=max(0.1, end - time.time())))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(method)

    def wait_event(self, name, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.ws.recv(timeout=max(0.1, end - time.time())))
            if msg.get("method") == name:
                return msg.get("params", {})
        raise TimeoutError(name)

    def open_html(self, html: str, timeout=60):
        f = Path(self.profile) / f"page{self._id}.html"
        f.write_text(html, encoding="utf-8")
        self.call("Page.navigate", url=f.as_uri())
        self.wait_event("Page.loadEventFired", timeout)

    def evaluate(self, expression: str, timeout=60):
        r = self.call("Runtime.evaluate", timeout=timeout, expression=expression, awaitPromise=True,
                      returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
        return r.get("result", {}).get("value")

    def wait_for(self, expression: str, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            if self.evaluate(expression):
                return
            time.sleep(0.2)
        raise TimeoutError(expression)

    def screenshot_element(self, selector: str, path: str | Path):
        box = self.evaluate(
            f"(() => {{ const r = document.querySelector({json.dumps(selector)}).getBoundingClientRect();"
            f" return [r.x + window.scrollX, r.y + window.scrollY, r.width, r.height]; }})()")
        x, y, w, h = box
        r = self.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                      clip={"x": x, "y": y, "width": w, "height": h, "scale": 1})
        Path(path).write_bytes(base64.b64decode(r["data"]))
