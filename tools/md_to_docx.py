"""Chuyển báo cáo Markdown → Word (.docx) có nhúng ảnh, định dạng theo kiểu báo cáo đồ án.

    python tools/md_to_docx.py docs/report/bao_cao.md            # → docs/report/bao_cao.docx

Bước 1 (mọi hệ điều hành): Markdown → HTML (thư viện `markdown`, CSS Times New Roman 13 pt).
Bước 2 (Windows có Microsoft Word): mở HTML bằng Word qua COM (PowerShell), nhúng ảnh vào tài liệu, lưu .docx.
Không có Word: mở file .html sinh ra bằng Word/LibreOffice và "Lưu thành .docx".
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import markdown

CSS = """
body { font-family: 'Times New Roman', serif; font-size: 13pt; line-height: 1.4; }
h1 { font-size: 18pt; text-align: center; }
h2 { font-size: 16pt; page-break-before: always; margin-top: 0; }
h3 { font-size: 14pt; }
h4 { font-size: 13pt; font-style: italic; }
table { border-collapse: collapse; margin: 6pt 0; }
th, td { border: 1px solid #777; padding: 3pt 6pt; font-size: 11pt; vertical-align: top; }
th { background: #DCE6EE; }
code, pre { font-family: Consolas, monospace; font-size: 10pt; }
pre { background: #F3F3F3; padding: 6pt; }
blockquote { border-left: 3pt solid #C0392B; margin-left: 0; padding-left: 8pt; color: #333; }
em { color: #333; }
"""

PS = r"""
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
  $doc = $word.Documents.Open('{html}', $false, $true)
  foreach ($s in @($doc.InlineShapes)) {
    if ($s.LinkFormat -ne $null) { $s.LinkFormat.SavePictureWithDocument = $true; $s.LinkFormat.BreakLink() }
  }
  # khổ A4, lề 3/2/2,5/2,5 cm (trái/phải/trên/dưới) theo thể thức báo cáo
  $ps = $doc.PageSetup
  $ps.PaperSize = 7; $ps.LeftMargin = 85.05; $ps.RightMargin = 56.7; $ps.TopMargin = 70.9; $ps.BottomMargin = 70.9
  # mọi hình giãn theo bề rộng vùng in, nhưng không cao quá 60 % trang (giữ tỉ lệ)
  $maxw = $ps.PageWidth - $ps.LeftMargin - $ps.RightMargin
  $maxh = ($ps.PageHeight - $ps.TopMargin - $ps.BottomMargin) * 0.6
  foreach ($s in @($doc.InlineShapes)) {
    if ($s.Type -ne 3 -and $s.Type -ne 4) { continue }  # chỉ ảnh (bỏ qua đường kẻ ngang <hr>)
    $s.LockAspectRatio = -1
    $ratio = $s.Height / $s.Width
    $w = $maxw
    if ($w * $ratio -gt $maxh) { $w = $maxh / $ratio }
    $s.Width = $w
  }
  $doc.SaveAs2('{docx}', 16)
  $doc.Close($false)
} finally { $word.Quit() }
"""


def main(src: str):
    md_path = Path(src).resolve()
    html_path = md_path.with_suffix(".html")
    docx_path = md_path.with_suffix(".docx")
    body = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "sane_lists"])
    html_path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>{md_path.stem}</title>"
                         f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    print("HTML:", html_path)
    if sys.platform != "win32":
        print("Không phải Windows: mở file HTML bằng Word/LibreOffice và lưu thành .docx")
        return
    script = PS.replace("{html}", str(html_path)).replace("{docx}", str(docx_path))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("Word COM lỗi — mở file HTML bằng Word và lưu thành .docx")
    html_path.unlink(missing_ok=True)
    print("DOCX:", docx_path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/report/bao_cao.md")
