import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

AGG_COLS = """avg(temp_dht) AS temp_dht, avg(hum) AS hum, avg(temp_bmp) AS temp_bmp, avg(pressure) AS pressure,
    avg(pressure_msl) AS pressure_msl, avg(lux) AS lux, avg(dew_point) AS dew_point, max(rain_level) AS rain_level,
    avg(gas_ppm) AS gas_ppm, max(gas_ppm) AS gas_ppm_max, avg(gas_rs_r0) AS gas_rs_r0, max(edge_risk) AS edge_risk,
    count(*) AS n"""


def _has_timescale(bind) -> bool:
    if bind.dialect.name != "postgresql":
        return False
    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        return True
    except Exception:
        return False


def upgrade():
    from app.db.models import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if not _has_timescale(bind):
        return
    op.execute("SELECT create_hypertable('telemetry', 'ts', if_not_exists => TRUE, migrate_data => TRUE)")
    for name, bucket, start, every in [("telemetry_1m", "1 minute", "2 hours", "1 minute"),
                                       ("telemetry_10m", "10 minutes", "1 day", "10 minutes"),
                                       ("telemetry_1h", "1 hour", "3 days", "1 hour")]:
        op.execute(f"""CREATE MATERIALIZED VIEW IF NOT EXISTS {name} WITH (timescaledb.continuous) AS
            SELECT device_id, time_bucket('{bucket}', ts) AS bucket, {AGG_COLS}
            FROM telemetry GROUP BY device_id, bucket WITH NO DATA""")
        op.execute(f"""SELECT add_continuous_aggregate_policy('{name}', start_offset => INTERVAL '{start}',
            end_offset => INTERVAL '{bucket}', schedule_interval => INTERVAL '{every}', if_not_exists => TRUE)""")
    op.execute("SELECT add_retention_policy('telemetry', INTERVAL '90 days', if_not_exists => TRUE)")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for v in ("telemetry_1h", "telemetry_10m", "telemetry_1m"):
            op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {v} CASCADE")
    from app.db.models import Base
    Base.metadata.drop_all(bind=bind)
