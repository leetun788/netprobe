"""The three check types: ping, dns, http.

Each check function takes (target_dict, timeout_seconds) and returns a dict:
    {
        "up": bool,
        "latency_ms": float or None,
        "loss_percent": float or None,   # ping only
        "error": str or None,
    }

To add a new check type: write a function, register it in CHECK_FUNCS.
"""

import shutil
import socket
import subprocess
import time

import dns.resolver
import requests

def _short_err(e: Exception) -> str:
    """Last-resort error stringifier — keep it to ~50 chars."""
    s = type(e).__name__ + ": " + str(e)
    return s if len(s) <= 50 else s[:47] + "…"

# ------------------------------ ping -------------------------------------- #

_FPING_AVAILABLE = shutil.which("fping") is not None


def _ping_fping(host: str, timeout: float) -> dict:
    """Use fping (Linux/LXC). Sends 4 packets, reports loss and avg latency."""
    try:
        # -C 4 sends 4 packets; -q quiet; -t timeout per packet in ms
        result = subprocess.run(
            ["fping", "-C", "4", "-q", "-t", str(int(timeout * 1000)), host],
            capture_output=True,
            text=True,
            timeout=timeout * 5 + 1,
        )
        # fping writes per-host stats to stderr in the form:
        #   8.8.8.8 : 12.3 13.1 11.8 12.4
        # with "-" for lost packets.
        line = result.stderr.strip().split("\n")[-1]
        parts = line.split(":", 1)
        if len(parts) != 2:
            return {"up": False, "latency_ms": None, "loss_percent": 100.0,
                    "error": f"unparseable: {line!r}"}
        latencies = [p for p in parts[1].split() if p != "-"]
        lost = parts[1].split().count("-")
        total = lost + len(latencies)
        if total == 0:
            return {"up": False, "latency_ms": None, "loss_percent": 100.0,
                    "error": "no packets"}
        loss_pct = (lost / total) * 100
        avg_latency = (sum(float(x) for x in latencies) / len(latencies)) \
            if latencies else None
        return {
            "up": len(latencies) > 0,
            "latency_ms": avg_latency,
            "loss_percent": loss_pct,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {"up": False, "latency_ms": None, "loss_percent": 100.0,
                "error": "timeout"}
    except Exception as e:
        return {"up": False, "latency_ms": None, "loss_percent": 100.0,
                "error": str(e)}


def _ping_stub(host: str, timeout: float) -> dict:
    """Workstation fallback when fping isn't installed (e.g. Windows dev).

    Returns 'up' with placeholder latency so dashboard/metrics shape is correct.
    Real ICMP would need raw socket privileges; not worth it for local dev.
    """
    return {
        "up": True,
        "latency_ms": 0.0,
        "loss_percent": 0.0,
        "error": "stub (no fping)",
    }


def check_ping(target: dict, timeout: float) -> dict:
    host = target["host"]
    if _FPING_AVAILABLE:
        return _ping_fping(host, timeout)
    return _ping_stub(host, timeout)


# ------------------------------ dns --------------------------------------- #

def check_dns(target: dict, timeout: float) -> dict:
    host = target["host"]
    resolver_ip = target.get("resolver")
    resolver = dns.resolver.Resolver(configure=resolver_ip is None)
    if resolver_ip:
        resolver.nameservers = [resolver_ip]
    resolver.lifetime = timeout
    resolver.timeout = timeout
    start = time.perf_counter()
    try:
        resolver.resolve(host, "A")
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"up": True, "latency_ms": elapsed_ms,
                "loss_percent": None, "error": None}
    except dns.resolver.NXDOMAIN:
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": "NXDOMAIN"}
    except dns.resolver.NoAnswer:
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": "no answer"}
    except dns.exception.Timeout:
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": "DNS timeout"}
    except Exception as e:
        return {"up": False, "latency_ms": None,
                "loss_percent": None, "error": _short_err(e)}


# ------------------------------ http -------------------------------------- #

def check_http(target: dict, timeout: float) -> dict:
    url = target["url"]
    start = time.perf_counter()
    try:
        # HEAD where possible to avoid downloading bodies; fall back to GET if
        # the server doesn't support HEAD (some block it).
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            r = requests.get(url, timeout=timeout, allow_redirects=True,
                             stream=True)
            r.close()
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"up": r.status_code < 400, "latency_ms": elapsed_ms,
                "loss_percent": None,
                "error": None if r.status_code < 400 else f"HTTP {r.status_code}"}
    except requests.exceptions.ConnectTimeout:
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": "connect timeout"}
    except requests.exceptions.ReadTimeout:
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": "read timeout"}
    except requests.exceptions.SSLError:
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": "SSL error"}
    except requests.exceptions.ConnectionError as e:
        # Could be DNS failure, connection refused, reset. Try to disambiguate
        # from the underlying error message, but bail to a short tag if not.
        msg = str(e).lower()
        if "name or service not known" in msg or "getaddrinfo failed" in msg \
                or "nodename nor servname" in msg:
            return {"up": False, "latency_ms": None, "loss_percent": None,
                    "error": "DNS failed"}
        if "connection refused" in msg:
            return {"up": False, "latency_ms": None, "loss_percent": None,
                    "error": "refused"}
        if "connection reset" in msg or "reset by peer" in msg:
            return {"up": False, "latency_ms": None, "loss_percent": None,
                    "error": "reset"}
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": "connect failed"}
    except Exception as e:
        return {"up": False, "latency_ms": None,
                "loss_percent": None, "error": _short_err(e)}


# ----------------------------- registry ----------------------------------- #

CHECK_FUNCS = {
    "ping": check_ping,
    "dns": check_dns,
    "http": check_http,
}


def run_check(target: dict, timeouts: dict) -> dict:
    fn = CHECK_FUNCS.get(target["type"])
    if fn is None:
        return {"up": False, "latency_ms": None, "loss_percent": None,
                "error": f"unknown check type: {target['type']}"}
    timeout = timeouts.get(target["type"], 5)
    return fn(target, timeout)