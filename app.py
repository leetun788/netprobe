"""netprobe entrypoint.

Loads config.yaml, initializes STATE, starts background loops, serves Flask.
"""

import logging
import sys
import time

import yaml
from flask import Flask, jsonify

import loop
from state import LOCK, STATE

from routes_html import bp as html_bp
from routes_metrics import bp as metrics_bp
from routes_state import bp as state_bp
from routes_status import bp as status_bp


def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_state(config):
    with LOCK:
        STATE["instance"] = config.get("instance", "unknown")
        STATE["wan_info"] = {
            item["id"]: {"value": None, "error": "not yet gathered",
                         "last_refresh": 0}
            for item in config.get("wan_info", {}).get("items", [])
        }
        STATE["categories"] = {
            cat_id: {
                "label": cat["label"],
                "up": False,
                "targets": {
                    t["id"]: {
                        "label": t["label"], "type": t["type"],
                        "up": False, "latency_ms": None, "loss_percent": None,
                        "last_refresh": 0, "error": "not yet probed",
                    }
                    for t in cat["targets"]
                },
            }
            for cat_id, cat in config["categories"].items()
        }
        STATE["config_loaded_at"] = time.time()


def create_app():
    app = Flask(__name__)
    app.register_blueprint(html_bp)
    app.register_blueprint(state_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(status_bp)

    @app.route("/wan_info/refresh", methods=["POST"])
    def wan_info_refresh():
        loop.trigger_wan_info_refresh()
        return jsonify({"ok": True, "message": "refresh triggered"})

    return app


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("netprobe")

    try:
        config = load_config()
    except FileNotFoundError:
        log.error("config.yaml not found in current directory")
        sys.exit(1)
    except yaml.YAMLError as e:
        log.error("config.yaml parse error: %s", e)
        sys.exit(1)

    init_state(config)
    log.info("Loaded config: instance=%s, %d wan_info items, %d categories",
             config.get("instance"),
             len(config.get("wan_info", {}).get("items", [])),
             len(config["categories"]))

    loop.start(config)

    app = create_app()
    host = config.get("listen_host", "127.0.0.1")
    port = config.get("listen_port", 8080)
    log.info("Listening on http://%s:%d", host, port)
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()