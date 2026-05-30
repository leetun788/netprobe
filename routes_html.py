"""/ — human dashboard. Renders templates/dashboard.html with current STATE.

Also serves the favicon inline at /favicon.svg so there's no static/ folder to
wire up — the SVG lives right here as a string.
"""

from flask import Blueprint, Response, render_template

from state import LOCK, STATE

bp = Blueprint("html", __name__)

# Radar-sweep mark. Green blip matches the dashboard's --up colour.
FAVICON_SVG = """<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="netprobe">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1220"/>
      <stop offset="1" stop-color="#111c33"/>
    </linearGradient>
    <radialGradient id="sweep" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="#34d399" stop-opacity="0"/>
      <stop offset="1" stop-color="#34d399" stop-opacity="0.55"/>
    </radialGradient>
  </defs>
  <rect x="2" y="2" width="60" height="60" rx="14" fill="url(#bg)"/>
  <g fill="none" stroke="#1f3b5c" stroke-width="2">
    <circle cx="32" cy="32" r="9"/>
    <circle cx="32" cy="32" r="17"/>
    <circle cx="32" cy="32" r="24"/>
  </g>
  <path d="M32 32 L32 6 A26 26 0 0 1 54.5 19 Z" fill="url(#sweep)"/>
  <g stroke="#1f3b5c" stroke-width="1.5">
    <line x1="32" y1="7" x2="32" y2="57"/>
    <line x1="7" y1="32" x2="57" y2="32"/>
  </g>
  <circle cx="32" cy="32" r="3.2" fill="#5eead4"/>
  <circle cx="45" cy="22" r="3.6" fill="#34d399"/>
  <circle cx="45" cy="22" r="6.5" fill="none" stroke="#34d399" stroke-width="1.5" opacity="0.5"/>
</svg>"""


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


@bp.route("/favicon.svg")
def favicon():
    return Response(FAVICON_SVG, mimetype="image/svg+xml")
