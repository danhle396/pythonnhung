from __future__ import annotations

import datetime as dt
import html
import logging
import smtplib
import threading
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings

log = logging.getLogger(__name__)
LEVEL_INFO = {0: ("🟢", "Bình thường"), 1: ("🟡", "Chú ý"), 2: ("🟠", "Cảnh báo"), 3: ("🔴", "NGUY HIỂM")}
TYPE_NAME = {"gas": "Khí dễ cháy / khói", "anomaly": "Bất thường khí (cloud AI)", "sensor_fault": "Lỗi cảm biến",
             "device_offline": "Mất kết nối thiết bị", "test": "Thử còi"}


class Notifier:
    def __init__(self, settings: Settings):
        self.s = settings
        self.sent: list[dict] = []
        self._offset = 0
        self.tz = ZoneInfo(settings.station_tz)

    @property
    def telegram_enabled(self):
        return bool(self.s.telegram_token and self.s.telegram_chat_id)

    def _api(self, method):
        return f"https://api.telegram.org/bot{self.s.telegram_token}/{method}"

    def format_alert(self, a, reminder=False) -> str:
        emoji, name = LEVEL_INFO.get(a.level, ("⚪", str(a.level)))
        ts = a.ts if a.ts.tzinfo else a.ts.replace(tzinfo=dt.timezone.utc)
        lines = [f"{emoji} <b>{'[NHẮC LẠI] ' if reminder else ''}{name}</b> — {TYPE_NAME.get(a.type, a.type)}",
                 f"Thiết bị: <code>{html.escape(a.device_id)}</code> (VKU, Ngũ Hành Sơn, Đà Nẵng)",
                 f"Thời gian: {ts.astimezone(self.tz):%H:%M:%S %d/%m/%Y}"]
        if a.gas_ppm is not None:
            lines.append(f"Gas: <b>{a.gas_ppm:.0f} ppm</b>" + (f", AI score {a.score:.2f}" if a.score is not None else ""))
        if a.cause:
            lines.append("Nguyên nhân: " + html.escape(", ".join(a.cause)))
        lines.append(f"Nguồn: {a.source} | Cấp trước: {a.prev_level}")
        if a.message:
            lines.append(html.escape(a.message))
        lines.append(f'<a href="{self.s.dashboard_url}">Mở dashboard</a>')
        return "\n".join(lines)

    def telegram(self, text: str, alert_id: int | None = None) -> bool:
        rec = {"channel": "telegram", "text": text, "alert_id": alert_id, "at": dt.datetime.now(dt.timezone.utc)}
        self.sent.append(rec)
        if not self.telegram_enabled:
            log.info("[telegram:dev] %s", text.replace("\n", " | "))
            return False
        body = {"chat_id": self.s.telegram_chat_id, "text": text, "parse_mode": "HTML",
                "disable_web_page_preview": True}
        if alert_id is not None:
            body["reply_markup"] = {"inline_keyboard": [[{"text": "✅ Đã xử lý", "callback_data": f"ack:{alert_id}"}]]}
        try:
            r = httpx.post(self._api("sendMessage"), json=body, timeout=10)
            ok = r.status_code == 200 and r.json().get("ok", False)
            if not ok:
                log.warning("Telegram lỗi: %s", r.text[:200])
            return ok
        except Exception as e:
            log.warning("Telegram lỗi: %s", e)
            return False

    def email(self, subject: str, body: str) -> bool:
        self.sent.append({"channel": "email", "text": subject, "at": dt.datetime.now(dt.timezone.utc)})
        if not (self.s.smtp_host and self.s.alert_email_to):
            log.info("[email:dev] %s", subject)
            return False
        msg = MIMEText(body, "html", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, self.s.smtp_user, self.s.alert_email_to
        try:
            with smtplib.SMTP_SSL(self.s.smtp_host, self.s.smtp_port, timeout=15) as smtp:
                smtp.login(self.s.smtp_user, self.s.smtp_pass)
                smtp.sendmail(self.s.smtp_user, self.s.alert_email_to.split(","), msg.as_string())
            return True
        except Exception as e:
            log.warning("Email lỗi: %s", e)
            return False

    def poll_forever(self, on_ack, stop: threading.Event):
        if not self.telegram_enabled:
            return
        while not stop.is_set():
            try:
                r = httpx.get(self._api("getUpdates"), params={"offset": self._offset, "timeout": 25,
                                                              "allowed_updates": '["callback_query"]'}, timeout=35)
                for upd in r.json().get("result", []):
                    self._offset = upd["update_id"] + 1
                    cq = upd.get("callback_query")
                    if not cq or not str(cq.get("data", "")).startswith("ack:"):
                        continue
                    alert_id = int(cq["data"].split(":", 1)[1])
                    user = cq.get("from", {}).get("username") or str(cq.get("from", {}).get("id"))
                    ok = on_ack(alert_id, f"telegram:{user}")
                    httpx.post(self._api("answerCallbackQuery"),
                               json={"callback_query_id": cq["id"], "text": "Đã xác nhận ✅" if ok else "Không tìm thấy"},
                               timeout=10)
                    msg = cq.get("message")
                    if msg and ok:
                        httpx.post(self._api("editMessageReplyMarkup"),
                                   json={"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                         "reply_markup": {"inline_keyboard": [[{"text": f"✅ {user} đã xử lý",
                                                                                "callback_data": "noop"}]]}},
                                   timeout=10)
            except Exception as e:
                log.debug("poll lỗi: %s", e)
                stop.wait(5)
