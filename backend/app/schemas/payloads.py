from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PHYS_RANGES = {
    "temp_dht": (-10, 60), "temp_bmp": (-10, 60), "hum": (0, 100), "pressure": (900, 1100),
    "pressure_msl": (900, 1100), "lux": (0, 120000), "gas_ppm": (0, 100000), "gas_rs_r0": (0, 100),
    "dew_point": (-30, 40), "heat_index": (-10, 80), "rain_level": (0, 3), "rain_raw": (0, 4095),
    "gas_raw": (0, 3400), "edge_score": (0, 1), "edge_risk": (0, 3),
}


def _to_dt(v):
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    if v in (None, 0):
        return dt.datetime.now(dt.timezone.utc)
    return dt.datetime.fromtimestamp(float(v), tz=dt.timezone.utc)


class TelemetryIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    device_id: str = Field(min_length=1, max_length=64)
    ts: dt.datetime
    seq: int = Field(ge=0)
    temp_dht: float | None = None
    hum: float | None = None
    temp_bmp: float | None = None
    pressure: float | None = None
    pressure_msl: float | None = None
    lux: float | None = None
    dew_point: float | None = None
    heat_index: float | None = None
    rain_raw: int | None = None
    rain_level: int | None = None
    gas_raw: float | None = None
    gas_rs_r0: float | None = None
    gas_ppm: float | None = None
    gas_slope: float | None = None
    edge_risk: int | None = None
    edge_score: float | None = None
    fw: str | None = None
    model_ver: str | None = None
    rejected: list[str] = Field(default_factory=list)

    @field_validator("ts", mode="before")
    @classmethod
    def _ts(cls, v):
        return _to_dt(v)

    @model_validator(mode="after")
    def _ranges(self):
        for k, (lo, hi) in PHYS_RANGES.items():
            v = getattr(self, k, None)
            if v is not None and not (lo <= v <= hi):
                self.rejected.append(f"{k}={v}")
                setattr(self, k, None)
        return self

    def extra_fields(self) -> dict[str, Any]:
        ex = dict(self.model_extra or {})
        if self.rejected:
            ex["rejected"] = self.rejected
        return ex


class AlertIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    device_id: str
    ts: dt.datetime
    seq: int | None = None
    type: str = "gas"
    level: int = Field(ge=0, le=3)
    prev_level: int | None = Field(default=None, ge=0, le=3)
    cause: list[str] = Field(default_factory=list)
    gas_ppm: float | None = None
    score: float | None = None
    action: list[str] = Field(default_factory=list)

    @field_validator("ts", mode="before")
    @classmethod
    def _ts(cls, v):
        return _to_dt(v)


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    state: str = "online"
    device_id: str | None = None
    rssi: int | None = None
    uptime_s: int | None = None
    free_heap: int | None = None
    fw: str | None = None
    model_ver: str | None = None


class AckIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    device_id: str | None = None
    ref: str
    id: str | None = None
    ok: bool = True
    msg: str | None = None


class DeviceConfigIn(BaseModel):
    th1: float | None = Field(default=None, gt=0, lt=10000)
    th2: float | None = Field(default=None, gt=0, lt=10000)
    th3: float | None = Field(default=None, gt=0, lt=10000)
    slope1: float | None = Field(default=None, gt=0)
    dtemp3: float | None = Field(default=None, gt=0)
    hyst: float | None = Field(default=None, ge=0, lt=0.5)
    debounce_up: int | None = Field(default=None, ge=1, le=30)
    debounce_down: int | None = Field(default=None, ge=1, le=60)
    telemetry_ms: int | None = Field(default=None, ge=1000, le=600000)
    mode: str | None = Field(default=None, pattern="^(rule|model|hybrid)$")
    r0_kohm: float | None = Field(default=None, gt=0.1, lt=1000)

    @model_validator(mode="after")
    def _order(self):
        th = [self.th1, self.th2, self.th3]
        given = [t for t in th if t is not None]
        if len(given) == 3 and not (th[0] < th[1] < th[2]):
            raise ValueError("cần th1 < th2 < th3")
        return self


class CommandIn(BaseModel):
    cmd: str = Field(pattern="^(mute|test_alarm|calibrate|reboot|escalate|ota)$")
    level: int | None = Field(default=None, ge=0, le=3)
    url: str | None = Field(default=None, pattern="^https?://", max_length=190)


class AckRequest(BaseModel):
    by: str | None = None
