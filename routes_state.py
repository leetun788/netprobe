"""/state — full JSON dump of current state. Used by the dashboard JS
   to refresh without a page reload, and handy for ad-hoc debugging."""

from flask import Blueprint, jsonify

from state import LOCK, STATE

bp = Blueprint("state", __name__)


@bp.route("/state")
def get_state():
    with LOCK:
        # jsonify deep-copies via serialization, so releasing the lock here is fine.
        return jsonify(STATE)