"""/metrics — Prometheus text exposition format.

Comments (lines starting with #) and blank lines are ignored by Prometheus,
so we use them liberally to organize the output for humans reading it directly
(e.g. `curl http://probe:8080/metrics`). HELP lines describe each metric;
separator banners group related series.
"""

from flask import Blueprint, Response

from state import LOCK, STATE
from version import __version__

bp = Blueprint("metrics", __name__)


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _banner(title):
    """Visual section divider. ~60 char wide, easy to spot when scrolling."""
    bar = "-" * 60
    return [f"# {bar}", f"# {title}", f"# {bar}"]


@bp.route("/metrics")
def metrics():
    lines = []
    with LOCK:
        instance = STATE["instance"]

        # netprobe_build_info: version stamp per probe (Prometheus info pattern —
        # value is always 1, the useful data is in the version label).
        lines += [
            "# HELP netprobe_build_info netprobe version running on this probe.",
            "# TYPE netprobe_build_info gauge",
            f'netprobe_build_info{{instance="{_esc(instance)}",version="{_esc(__version__)}"}} 1',
        ]

        # =========================================================== #
        # WAN INFO — slow-changing facts about this probe's WAN egress
        # =========================================================== #
        lines += [""]
        lines += _banner("WAN INFO — gateway, exit IP, geolocation")
        lines += [
            "# These series describe where this probe sits on the network and",
            "# where its traffic appears to exit to the public internet.",
            "# Refreshed slowly (default every 10 minutes) — values change rarely.",
            "",
            "# HELP netprobe_wan_info The current value of a WAN info item. The actual value (an IP, a city, etc.) is carried as the `value` label; the metric itself is always 1 when the item has a value.",
            "# TYPE netprobe_wan_info gauge",
            "# HELP netprobe_wan_info_ok 1 if this WAN info item was successfully gathered on the last refresh, 0 if it failed.",
            "# TYPE netprobe_wan_info_ok gauge",
            "# HELP netprobe_wan_info_last_refresh_timestamp Unix timestamp of the last successful refresh of this WAN info item.",
            "# TYPE netprobe_wan_info_last_refresh_timestamp gauge",
        ]
        for item_id, item in STATE["wan_info"].items():
            ok = 1 if item.get("value") is not None else 0
            if item.get("value") is not None:
                lines.append(
                    f'netprobe_wan_info{{instance="{instance}",'
                    f'item_id="{item_id}",value="{_esc(item["value"])}"}} 1'
                )
            lines.append(
                f'netprobe_wan_info_ok{{instance="{instance}",'
                f'item_id="{item_id}"}} {ok}'
            )
            lines.append(
                f'netprobe_wan_info_last_refresh_timestamp{{instance="{instance}",'
                f'item_id="{item_id}"}} {int(item.get("last_refresh", 0))}'
            )

        # =========================================================== #
        # CATEGORIES — rollup status, one per logical group of targets
        # =========================================================== #
        lines += ["", ""]
        lines += _banner("CATEGORY ROLLUPS — overall up/down per group")
        lines += [
            "# A category is up only when every target inside it is up.",
            "# Useful for at-a-glance alerts: \"is anything in the 'web' group failing?\"",
            "",
            "# HELP netprobe_category_up 1 if every target in this category is currently up, 0 if any target is down.",
            "# TYPE netprobe_category_up gauge",
        ]
        for cat_id, cat in STATE["categories"].items():
            lines.append(
                f'netprobe_category_up{{instance="{instance}",'
                f'category="{cat_id}",category_label="{_esc(cat["label"])}"}} '
                f'{1 if cat["up"] else 0}'
            )

        # =========================================================== #
        # TARGETS — per-target probe results
        # =========================================================== #
        lines += ["", ""]
        lines += _banner("TARGETS — per-host probe results")
        lines += [
            "# One set of series per target. Refreshed every check_interval_seconds",
            "# (default 30s). Labels: instance, category, target_id, target_label, type.",
            "#   type=ping  — ICMP via fping (stubbed on Windows)",
            "#   type=http  — HTTPS reachability of a URL",
            "#   type=dns   — name resolution against a specific resolver",
            "",
            "# HELP netprobe_target_up 1 if the last probe of this target succeeded, 0 if it failed.",
            "# TYPE netprobe_target_up gauge",
            "# HELP netprobe_target_latency_ms Time the last successful probe took, in milliseconds. Only emitted when the target is up.",
            "# TYPE netprobe_target_latency_ms gauge",
            "# HELP netprobe_target_loss_percent Percentage of attempts that failed in the last check. For ping, packet loss; for http/dns, the share of retries that failed.",
            "# TYPE netprobe_target_loss_percent gauge",
        ]
        for cat_id, cat in STATE["categories"].items():
            for t_id, t in cat["targets"].items():
                labels = (
                    f'instance="{instance}",category="{cat_id}",'
                    f'target_id="{t_id}",target_label="{_esc(t["label"])}",'
                    f'type="{t["type"]}"'
                )
                lines.append(f'netprobe_target_up{{{labels}}} {1 if t["up"] else 0}')
                if t["up"] and t["latency_ms"] is not None:
                    lines.append(
                        f'netprobe_target_latency_ms{{{labels}}} {t["latency_ms"]:.1f}'
                    )
                if t["loss_percent"] is not None:
                    lines.append(
                        f'netprobe_target_loss_percent{{{labels}}} {t["loss_percent"]:.0f}'
                    )

        lines += [""]

    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")