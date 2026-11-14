from __future__ import annotations

USAGE = """Căn thẳng cột các bảng Markdown (đệm khoảng trắng theo độ rộng hiển thị, hỗ trợ tiếng Việt).

Chỉ đổi khoảng trắng: nội dung ô, số cột và kiểu căn lề (:---, ---:, :---:) giữ nguyên ⇒ bảng hiển thị y hệt.
Bỏ qua các khối code (``` hoặc ~~~).

    python -m aiot_ml.mdtable docs/report/*.md README.md      # sửa tại chỗ
    python -m aiot_ml.mdtable --check docs/report/*.md         # chỉ báo file nào chưa căn (exit 1)
Các script sinh báo cáo (train_forecast, train_gas_edge, train_anomaly, tools/load_test.py) gọi align_tables()
trước khi ghi file.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

_PIPE = re.compile(r"(?<!\\)\|")
_DELIM_CELL = re.compile(r"^:?-+:?$")


def display_width(s: str) -> int:
    w = 0
    for ch in s:
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in _PIPE.split(s)]


def _is_delim_row(cells: list[str]) -> bool:
    return bool(cells) and all(_DELIM_CELL.match(c) for c in cells)


def _pad(text: str, width: int, align: str) -> str:
    gap = width - display_width(text)
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def _format_table(lines: list[str]) -> list[str]:
    indent = lines[0][: len(lines[0]) - len(lines[0].lstrip())]
    rows = [_split_row(l) for l in lines]
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    delim = rows[1]
    aligns = []
    for c in delim:
        if c.startswith(":") and c.endswith(":") and len(c) > 1:
            aligns.append("center")
        elif c.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("left")
    widths = [3] * ncol
    for i, r in enumerate(rows):
        if i == 1:
            continue
        for j, c in enumerate(r):
            widths[j] = max(widths[j], display_width(c))
    out = []
    for i, r in enumerate(rows):
        if i == 1:
            cells = []
            for w, a in zip(widths, aligns):
                if a == "center":
                    cells.append(":" + "-" * (w - 2) + ":")
                elif a == "right":
                    cells.append("-" * (w - 1) + ":")
                elif delim[len(cells)].startswith(":"):
                    cells.append(":" + "-" * (w - 1))
                else:
                    cells.append("-" * w)
        else:
            cells = [_pad(c, w, "left" if i == 0 else a) for c, w, a in zip(r, widths, aligns)]
        out.append(indent + "| " + " | ".join(cells) + " |")
    return out


def align_tables(text: str) -> str:
    if "\r\n" in text:
        return align_tables(text.replace("\r\n", "\n")).replace("\n", "\r\n")
    lines = text.split("\n")
    out: list[str] = []
    fence = None
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        m = re.match(r"^(`{3,}|~{3,})", s)
        if m:
            if fence is None:
                fence = m.group(1)[0]
            elif s.startswith(fence * 3):
                fence = None
            out.append(line)
            i += 1
            continue
        if (fence is None and s.startswith("|") and i + 1 < len(lines)
                and lines[i + 1].strip().startswith("|") and _is_delim_row(_split_row(lines[i + 1]))):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.extend(_format_table(lines[i:j]))
            i = j
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--check", action="store_true", help="không sửa, chỉ liệt kê file chưa căn")
    a = ap.parse_args(argv)
    bad = 0
    for f in a.files:
        p = Path(f)
        with open(p, encoding="utf-8", newline="") as fh:
            old = fh.read()
        new = align_tables(old)
        if new != old:
            bad += 1
            if a.check:
                print(f"chưa căn: {p}")
            else:
                p.write_text(new, encoding="utf-8", newline="")
                print(f"đã căn: {p}")
    return 1 if (a.check and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
