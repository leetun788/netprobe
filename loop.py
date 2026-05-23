"""Background loops. One for checks (fast), one for wan_info (slow, wakeable)."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from checks import run_check
from info import gather_all
from state import LOCK, STATE

log = logging.getLogger("netprobe.loop")

_wan_info_wake = threading.Event()


def _run_check_pass(config):
    timeouts = config.get("timeouts", {})
    work = [(cat_id, t) for cat_id, cat in config["categories"].items()
            for t in cat["targets"]]
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(run_check, t, timeouts): (cat_id, t)
                   for cat_id, t in work}
        for fut in as_completed(futures):
            cat_id, target = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                result = {"up": False, "latency_ms": None,
                          "loss_percent": None, "error": f"exception: {e}"}
            with LOCK:
                t_state = STATE["categories"][cat_id]["targets"][target["id"]]
                t_state.update({
                    "up": result["up"],
                    "latency_ms": result["latency_ms"],
                    "loss_percent": result["loss_percent"],
                    "error": result["error"],
                    "last_refresh": time.time(),
                })
    with LOCK:
        for cat in STATE["categories"].values():
            cat["up"] = all(t["up"] for t in cat["targets"].values())


def _check_loop(config):
    interval = config.get("check_interval_seconds", 30)
    log.info("Check loop starting, interval=%ss", interval)
    while True:
        start = time.time()
        try:
            _run_check_pass(config)
        except Exception:
            log.exception("Check pass failed")
        time.sleep(max(0, interval - (time.time() - start)))


def _run_wan_info_pass(config):
    with LOCK:
        current = dict(STATE["wan_info"])
    new_info = gather_all(config, current)
    with LOCK:
        STATE["wan_info"] = new_info


def _wan_info_loop(config):
    interval = config.get("wan_info", {}).get("refresh_interval_seconds", 600)
    log.info("WAN info loop starting, interval=%ss", interval)
    while True:
        start = time.time()
        try:
            _run_wan_info_pass(config)
        except Exception:
            log.exception("WAN info pass failed")
        wait_for = max(0, interval - (time.time() - start))
        _wan_info_wake.wait(timeout=wait_for)
        _wan_info_wake.clear()


def trigger_wan_info_refresh():
    """Wake the wan_info loop now. Called by /wan_info/refresh."""
    _wan_info_wake.set()


def start(config):
    threading.Thread(target=_check_loop, args=(config,), daemon=True,
                     name="netprobe-checks").start()
    threading.Thread(target=_wan_info_loop, args=(config,), daemon=True,
                     name="netprobe-wan-info").start()