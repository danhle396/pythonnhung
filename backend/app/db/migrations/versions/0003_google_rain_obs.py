"""Bảng google_rain_obs: xác suất mưa Google nhập tay + đặc trưng ensemble để học hiệu chỉnh (miễn phí)."""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # 0001 tạo bảng từ models hiện tại (create_all) nên CSDL mới đã có bảng này
    if "google_rain_obs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "google_rain_obs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), index=True),
        sa.Column("valid_at", sa.DateTime(timezone=True), index=True),
        sa.Column("google_pct", sa.Float),
        sa.Column("features", sa.JSON),
        sa.Column("entered_by", sa.String(64)),
    )


def downgrade():
    op.drop_table("google_rain_obs")
