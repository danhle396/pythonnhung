# Load test — 50 thiết bị × 1.0 msg/s × 30 s (QoS 1)

| Chỉ số | Giá trị |
|---|---|
| Gửi / nhận | 1505 / 1505 |
| Mất gói (broker) | 0.000 % |
| Thông lượng | 50.2 msg/s |
| Độ trễ broker P50 | 1.7 ms |
| Độ trễ broker P95 | 3.4 ms |
| Độ trễ broker P99 | 4.4 ms |
| Bản ghi vào DB | 1505 (mất 0.000 %) |

## Môi trường: Docker Compose (Mosquitto 2.0.20 + TimescaleDB 2.17 / PG16 + backend + dashboard)

Chạy `docker compose up -d --build` trên Docker Desktop (Windows 11, WSL2, 20 luồng CPU, 8 GB cho VM);
`tools/load_test.py --port 11883 --devices 50 --duration 30 --rate 1 --qos 1 --api http://localhost:8000`.

Tài nguyên container lấy mẫu bằng `docker stats` (29 mẫu trong lúc chạy, % của 1 lõi):

| Container | CPU TB | CPU max | RAM |
|---|---|---|---|
| backend (FastAPI + ingest MQTT) | 9.8 % | 70.5 % | 133 MB |
| db (TimescaleDB) | 1.5 % | 6.7 % | 97 MB |
| mosquitto | 1.3 % | 4.8 % | 18 MB |
| dashboard (Streamlit) | 1.7 % | 11.8 % | 132 MB |

So với chạy SQLite trên Windows (`results_load_50.md`, CPU backend TB 61 %): ghi lô vào PostgreSQL/Timescale nhẹ hơn nhiều,
100 % bản ghi vào DB, độ trễ broker P95 ≈ 3.4 ms (qua lớp mạng Docker Desktop).
