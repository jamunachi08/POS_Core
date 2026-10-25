"""Network printers the operator added from a scan.

Kept in their own JSON file rather than written back into config.yaml:
YAML support is an optional extra, and rewriting a hand-edited config would
destroy its comments and ordering. The bridge loads this file after the
main config at startup, so a scan-added printer survives a restart.
"""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path

STORE = Path.home() / ".alphax-bridge" / "network-devices.json"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\- ]{0,63}$")


def _read() -> list[dict]:
    if not STORE.exists():
        return []
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    tmp.replace(STORE)


def _conf(name: str, host: str, port: int, profile: str) -> dict:
    return {
        "name": name,
        "kind": "printer",
        "profile": profile,
        "connection": {"transport": "network", "host": host, "port": port, "timeout": 3.0},
    }


def add_network_device(registry, body: dict) -> dict:
    name = str(body.get("name") or "").strip()
    host = str(body.get("host") or "").strip()
    port = int(body.get("port") or 9100)
    profile = str(body.get("profile") or "generic-network-escpos").strip()

    if not _NAME.match(name):
        raise ValueError("Device name: letters, digits, space, dot, dash or underscore.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError(f"'{host}' is not an IP address.")
    if not (ip.is_private or ip.is_link_local or ip.is_loopback):
        raise ValueError("Only private network addresses can be added.")
    if not 1 <= port <= 65535:
        raise ValueError("Port out of range.")
    if not registry.get_profile(profile):
        profile = "generic-network-escpos"

    conf = _conf(name, str(ip), port, profile)
    if registry.get(name):
        registry.remove(name)
    registry.add_device_from_config(conf)       # live: usable immediately

    rows = [r for r in _read() if r.get("name") != name] + [conf]
    _write(rows)                                 # durable: survives restart
    return {"ok": True, "device": name, "profile": profile, "persisted_to": str(STORE)}


def load_into(registry) -> int:
    n = 0
    for conf in _read():
        try:
            if not registry.get(conf.get("name")):
                registry.add_device_from_config(conf)
                n += 1
        except Exception:
            continue
    return n
