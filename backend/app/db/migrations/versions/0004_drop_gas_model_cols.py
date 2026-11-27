"""Bỏ các cột của mô hình AI khí (đã loại khỏi dự án: cảnh báo khí chỉ còn luật 4 mức).

telemetry.edge_score, telemetry.model_ver, alerts.score, devices.model_ver.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

COLS = [("telemetry", "edge_score", sa.Float), ("telemetry", "model_ver", sa.String(64)),
        ("alerts", "score", sa.Float), ("devices", "model_ver", sa.String(64))]


def _columns(table):
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    # 0001 tạo bảng từ models hiện tại (create_all) nên CSDL mới không có các cột này
    for table, col, _ in COLS:
        if col in _columns(table):
            op.drop_column(table, col)


def downgrade():
    for table, col, typ in COLS:
        if col not in _columns(table):
            op.add_column(table, sa.Column(col, typ, nullable=True))
