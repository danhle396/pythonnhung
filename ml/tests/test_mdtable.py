from aiot_ml.mdtable import align_tables, display_width


def test_display_width_vietnamese():
    assert display_width("Mô hình") == 7
    assert display_width("Mô hình") == 7


def test_align_keeps_cells_and_alignment():
    src = "x\n\n| Mô hình | a | b |\n|---|:---:|---:|\n| GBDT | **0.299** | 1 |\n| Persistence | 0.5 | 10 |\n"
    out = align_tables(src)
    rows = [l for l in out.splitlines() if l.startswith("|")]
    assert len({len(r) for r in rows}) == 1
    assert rows[1] == "| ----------- | :-------: | --: |"
    assert rows[2] == "| GBDT        | **0.299** |   1 |"
    assert align_tables(out) == out


def test_skip_code_fence_and_keep_crlf():
    fenced = "```\r\n| a | bb |\r\n|---|---|\r\n| ccc | d |\r\n```\r\n"
    assert align_tables(fenced) == fenced
    t = "| a | bb |\r\n|---|---|\r\n| ccc | d |\r\n"
    assert align_tables(t) == "| a   | bb  |\r\n| --- | --- |\r\n| ccc | d   |\r\n"


def test_escaped_pipe_stays_in_cell():
    out = align_tables("| k | v |\n|---|---|\n| a \\| b | 1 |\n")
    assert "| a \\| b | 1   |" in out
