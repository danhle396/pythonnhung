import ast
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "src" / "config.py"


def constants() -> dict:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def fw_version() -> str:
    return constants()["FW_VERSION"]
