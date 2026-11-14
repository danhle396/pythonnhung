"""Bỏ bảng nowcasts (nowcast Zambretti tại edge đã bị loại khỏi dự án)."""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS nowcasts")


def downgrade():
    op.create_table(
        "nowcasts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), index=True),
        sa.Column("ts", sa.DateTime(timezone=True), index=True),
        sa.Column("code", sa.Integer),
        sa.Column("text", sa.String(64)),
        sa.Column("trend", sa.Integer),
        sa.Column("trend_3h", sa.Float),
        sa.Column("zambretti", sa.String(2)),
    )
