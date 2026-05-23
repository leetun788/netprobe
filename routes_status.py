"""/status — compact push-format output: one `target_id:up|down` per line.

Suitable for Uptime Kuma push monitors and other simple status consumers.
Format intentionally minimal — no labels, no timestamps, just the IDs."""

from flask import Blueprint, Response

from state import LOCK, STATE

bp = Blueprint("status", __name__)


@bp.route("/status")
def status():
    lines = []
    with LOCK:
        for cat in STATE["categories"].values():
            for t_id, t in cat["targets"].items():
                lines.append(f"{t_id}:{'up' if t['up'] else 'down'}")
    return Response("\n".join(lines) + "\n", mimetype="text/plain")