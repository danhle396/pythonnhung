from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_cdp import Browser

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "report" / "figures" / "diagrams"
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"


def slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "_", s)[:40]
    return s.strip("_")


def blocks(md: Path):
    txt = md.read_text(encoding="utf-8").replace("\r\n", "\n")
    title = md.stem
    for m in re.finditer(r"^##\s+(.+)$|```mermaid\n([\s\S]*?)```", txt, re.M):
        if m.group(1):
            title = m.group(1).strip()
        else:
            yield slug(title), m.group(2)


PAGE = f"""<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#fff;overflow:hidden"><div id="c"></div>
<script src="{MERMAID_CDN}"></script></body></html>"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted((ROOT / "docs" / "architecture").glob("*.md"))
    with Browser() as b:
        b.open_html(PAGE)
        b.wait_for("typeof mermaid !== 'undefined'")
        b.evaluate("mermaid.initialize({startOnLoad: false, theme: 'neutral', fontFamily: 'Arial, sans-serif',"
                   " flowchart: {htmlLabels: true, curve: 'basis'}, sequence: {useMaxWidth: false}}); true")
        for md in files:
            for name, code in blocks(md):
                b.evaluate(f"(async () => {{ const r = await mermaid.render({json.dumps('m' + name)}, {json.dumps(code)});"
                           " const c = document.getElementById('c'); c.innerHTML = r.svg;"
                           " const s = c.querySelector('svg'); s.style.maxWidth = 'none'; s.style.background = '#fff';"
                           " return true; })()")
                out = OUT / f"{name}.png"
                b.screenshot_element("#c svg", out)
                print("ok", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
