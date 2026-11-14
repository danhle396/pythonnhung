import json

import config
import gas_model
from alert import BUZZER_CONTINUOUS, BUZZER_INTERMITTENT, LED_RED_BLINK, LED_RED_SOLID, LED_YELLOW
from compat import isnan

LEVEL_NAME = ("normal", "advisory", "warning", "danger")


def num(v, digits=2):
    if isnan(v):
        return None
    return round(float(v), digits)


def dumps(d):
    return json.dumps(d)


def telemetry(d, act, o, seq):
    return dumps({
        "device_id": config.DEVICE_ID, "ts": d.ts, "seq": seq,
        "temp_dht": num(d.temp_dht), "hum": num(d.hum), "temp_bmp": num(d.temp_bmp),
        "pressure": num(d.pressure), "pressure_msl": num(d.pressure_msl), "lux": num(d.lux, 1),
        "dew_point": num(d.dew), "heat_index": num(d.heat_index),
        "rain_raw": d.rain_mv, "rain_level": d.rain_level,
        "gas_raw": num(d.gas_mv, 0), "gas_rs_r0": num(d.mq2.ratio, 3), "gas_ppm": num(d.mq2.ppm, 1),
        "gas_slope": num(o.f[2] if o.f else 0.0, 2),
        "edge_risk": act.level, "edge_score": num(o.score, 3), "warming_up": o.warming_up,
        "sensor_ok": {"dht": d.dht_ok, "bmp": d.bmp_ok, "bh": d.bh_ok, "rain": d.rain_ok, "gas": d.gas_ok},
        "fw": config.FW_VERSION, "model_ver": gas_model.VERSION,
    })


def action_list(act):
    a = []
    if act.led == LED_RED_SOLID:
        a.append("led_red_solid")
    elif act.led == LED_RED_BLINK:
        a.append("led_red_blink")
    elif act.led == LED_YELLOW:
        a.append("led_yellow" if config.HAS_LED_YELLOW else "led_green_blink")
    else:
        a.append("led_green")
    if act.buzzer == BUZZER_CONTINUOUS:
        a.append("buzzer_continuous")
    elif act.buzzer == BUZZER_INTERMITTENT:
        a.append("buzzer_intermittent")
    if config.HAS_RELAY and act.relay:
        a.append("fan_on")
    return a


def alert_gas(d, act, o, seq, is_test, causes, latency_ms):
    return dumps({
        "device_id": config.DEVICE_ID, "ts": d.ts, "seq": seq,
        "type": "test" if is_test else "gas",
        "level": act.level, "prev_level": act.prev_level, "level_name": LEVEL_NAME[act.level & 3],
        "cause": causes, "gas_ppm": num(d.mq2.ppm, 0), "score": num(o.score, 3),
        "rule_level": o.rule_level, "model_level": o.model_level,
        "action": action_list(act), "edge_latency_ms": latency_ms,
    })


def sensor_fault(d, level, seq):
    return dumps({
        "device_id": config.DEVICE_ID, "ts": d.ts, "seq": seq, "type": "sensor_fault", "sensor": "mq2",
        "fault": d.gas_fault,
        "level": level, "prev_level": level,
    })
def ack(ref, cmd_id, ok, msg, ts):
    d = {"device_id": config.DEVICE_ID, "ts": ts, "ref": ref, "ok": ok, "msg": msg}
    if cmd_id:
        d["id"] = cmd_id
    return dumps(d)


def status(info):
    d = {"state": "online", "device_id": config.DEVICE_ID, "fw": config.FW_VERSION, "model_ver": gas_model.VERSION}
    d.update(info)
    return dumps(d)
