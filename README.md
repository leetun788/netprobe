# netprobe

Stateless network probe for home lab monitoring. Probes targets via ICMP, HTTP, and DNS, exposes results on a small Flask web server.

## Endpoints

- `/` — human dashboard
- `/metrics` — Prometheus text format for Grafana
- `/status` — compact `id:up|down` lines for Uptime Kuma push monitors
- `/state` — full JSON state dump
- `POST /wan_info/refresh` — force immediate WAN info refresh

## Run

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
# or: source .venv/bin/activate  # Linux

pip install -r requirements.txt
cp config.example.yaml config.yaml   # then edit
python app.py
```