"""Xuất file .drawio thành PNG bằng viewer của diagrams.net chạy trong Edge/Chrome headless (qua tools/browser_cdp.py).
Không cần cài draw.io desktop; cần Internet để trình duyệt tải viewer-static.min.js.

    python tools/render_drawio.py docs/hardware/wiring.drawio [out.png]

File nhiều trang -> out-1.png, out-2.png, …
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_cdp import Browser  # noqa: E402

VIEWER = "https://viewer.diagrams.net/js/viewer-static.min.js"


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    src = Path(argv[0]).resolve()
    out = Path(argv[1]).resolve() if len(argv) > 1 else src.with_suffix(".png")
    xml = src.read_text(encoding="utf-8")
    pages = max(1, len(re.findall(r"<diagram[\s>]", xml)))
    with Browser(width=2000, height=1500, scale=2) as b:
        for i in range(pages):
            cfg = json.dumps({"highlight": "#0000ff", "nav": False, "resize": True, "toolbar": "", "edit": None,
                              "page": i, "xml": xml})
            b.open_html(f"""<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#fff;overflow:hidden"><div class="mxgraph" style="max-width:100%;" data-mxgraph="{html.escape(cfg)}"></div>
<script src="{VIEWER}"></script></body></html>""")
            b.wait_for("!!document.querySelector('.mxgraph svg')", timeout=30)
            time.sleep(1.0)  # chờ font và đường nối vẽ xong
            f = out.with_name(f"{out.stem}-{i + 1}.png") if pages > 1 else out
            b.screenshot_element(".mxgraph svg", f)
            print("Đã ghi", f)


if __name__ == "__main__":
    main()
