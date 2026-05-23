"""/ — human dashboard. Renders templates/dashboard.html with current STATE."""

from flask import Blueprint, render_template

from state import LOCK, STATE

bp = Blueprint("html", __name__)


@bp.route("/")
def dashboard():
    with LOCK:
        snapshot = {
            "instance": STATE["instance"],
            "wan_info": STATE["wan_info"],
            "categories": STATE["categories"],
            "config_loaded_at": STATE["config_loaded_at"],
        }
    return render_template("dashboard.html", state=snapshot)