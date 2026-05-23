"""In-memory state. Mutated by loop.py, read by route handlers."""

import threading

STATE = {
    "instance": "unknown",
    "wan_info": {},      # {item_id: {value, error, last_refresh}}
    "categories": {},    # {cat_id: {label, up, targets: {...}}}
    "config_loaded_at": 0,
}

LOCK = threading.Lock()