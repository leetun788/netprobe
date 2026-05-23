"""Info gatherers — local_gateway, exit_ip, exit_geo.

Unlike checks, info items have a *value* (a string) not an up/down state.
Refreshed on a slower interval. Each gatherer returns:
    {"value": str or None, "error": str or None, "last_refresh": unix_timestamp}
"""

import platform
import re
import shutil
import subprocess
import time

import requests

_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")


# ----------------------------- gateway ------------------------------------ #

def _tracert_hop(hop_number: int, timeout: float = 15) -> dict:
    """Return the IP at the Nth hop of tracert. hop_number is 1-indexed."""
    if platform.system() == "Windows":
        cmd = ["tracert", "-h", str(hop_number), "-w", "1500", "-d", "8.8.8.8"]
    elif shutil.which("traceroute"):
        cmd = ["traceroute", "-n", "-m", str(hop_number), "-w", "2", "8.8.8.8"]
    else:
        return {"value": None, "error": "no tracert/traceroute available",
                "last_refresh": time.time()}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout)
        hop_lines = [
            ln.strip() for ln in result.stdout.splitlines()
            if ln.strip() and ln.strip()[0].isdigit()
        ]
        if len(hop_lines) < hop_number:
            return {"value": None,
                    "error": f"only {len(hop_lines)} hop(s) reached",
                    "last_refresh": time.time()}
        m = _IP_RE.search(hop_lines[hop_number - 1])
        if m:
            return {"value": m.group(1), "error": None,
                    "last_refresh": time.time()}
        return {"value": None, "error": f"no IP at hop {hop_number}",
                "last_refresh": time.time()}
    except subprocess.TimeoutExpired:
        return {"value": None, "error": "tracert timeout",
                "last_refresh": time.time()}
    except Exception as e:
        return {"value": None, "error": str(e)[:80],
                "last_refresh": time.time()}


def get_gateway(item: dict, _state_info: dict) -> dict:
    hop = item.get("hop", 2)
    return _tracert_hop(hop)


# ----------------------------- exit_ip ------------------------------------ #

def get_exit_ip(item: dict, _state_info: dict) -> dict:
    """Try each URL in order. First plausible IPv4 wins."""
    urls = item.get("urls") or ([item["url"]] if "url" in item else [])
    timeout = item.get("timeout", 5)
    last_error = "no urls configured"
    for url in urls:
        try:
            r = requests.get(url, timeout=timeout,
                             headers={"User-Agent": "netprobe/1.0"})
            r.raise_for_status()
            ip = r.text.strip()
            parts = ip.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255
                                       for p in parts):
                return {"value": ip, "error": None,
                        "last_refresh": time.time()}
            last_error = f"bad response from {url}"
        except Exception as e:
            last_error = f"{url}: {type(e).__name__}"
    return {"value": None, "error": last_error,
            "last_refresh": time.time()}


# ----------------------------- exit_geo ----------------------------------- #

def get_exit_geo(item: dict, state_info: dict) -> dict:
    """Geo-lookup the current exit_ip. URLs may contain {ip} placeholder."""
    exit_ip = state_info.get("exit_ip", {}).get("value")
    if not exit_ip:
        return {"value": None, "error": "exit_ip unknown",
                "last_refresh": time.time()}

    urls = item.get("urls") or ([item["url"]] if "url" in item else [])
    timeout = item.get("timeout", 5)
    last_error = "no urls configured"
    for url_tpl in urls:
        url = url_tpl.format(ip=exit_ip)
        try:
            r = requests.get(url, timeout=timeout,
                             headers={"User-Agent": "netprobe/1.0"})
            r.raise_for_status()
            data = r.json()
            # Normalize across providers — different services use different keys.
            asn     = data.get("asn") or data.get("as") or ""
            isp     = data.get("isp") or data.get("org") or ""
            country = (data.get("country_name") or data.get("country")
                       or data.get("country_code") or "")
            region  = (data.get("region_name") or data.get("region")
                       or data.get("province") or "")
            city    = data.get("city_name") or data.get("city") or ""
            parts = [str(p).strip() for p in (asn or isp, city, region, country)
                     if p and str(p).strip()]
            value = " — ".join(parts) if parts else "unknown"
            return {"value": value, "error": None,
                    "last_refresh": time.time()}
        except Exception as e:
            last_error = f"{url_tpl}: {type(e).__name__}"
    return {"value": None, "error": last_error,
            "last_refresh": time.time()}


# ----------------------------- registry ----------------------------------- #

INFO_FUNCS = {
    "gateway": get_gateway,
    "exit_ip": get_exit_ip,
    "exit_geo": get_exit_geo,
}


def gather_one(item: dict, state_info: dict) -> dict:
    fn = INFO_FUNCS.get(item["type"])
    if fn is None:
        return {"value": None, "error": f"unknown info type: {item['type']}",
                "last_refresh": time.time()}
    return fn(item, state_info)


def gather_all(config: dict, state_info: dict) -> dict:
    """Run all wan_info items. Items with depends_on run after their dependency."""
    items = config.get("wan_info", {}).get("items", [])
    ordered = sorted(items, key=lambda i: 0 if not i.get("depends_on") else 1)
    new_info = dict(state_info)
    for item in ordered:
        new_info[item["id"]] = gather_one(item, new_info)
    return new_info