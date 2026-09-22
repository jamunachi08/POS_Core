"""LAN discovery for the AlphaX POS Bridge.

Answers "what hardware is on this shop's network?" from the one place that
can answer it: a machine *inside* the network. The POS server cannot — it
lives in a data centre and a 192.168.x.x address is not routable to it. A
browser cannot either — it has no raw sockets, and an HTTPS page may not
fetch plain-HTTP LAN addresses. The bridge can, so the bridge does.

What it finds
-------------
  printers       anything answering on 9100 (raw / JetDirect), 515 (LPD)
                 or 631 (IPP). Model from SNMP where the device allows it,
                 otherwise from its web page title.
  AlphaX bridges other tills running this bridge with LAN access on. Only
                 their public ``/hello`` is read — name, version, hostname —
                 which the POS server uses to match the address to a
                 terminal record. Full hardware detail for that PC reaches
                 the server through that PC's own authenticated heartbeat,
                 never through a neighbour.
  other devices  anything else that answered, reported as-is.

What it will not do
-------------------
  * Scan public addresses. Private, link-local and loopback ranges only.
  * Scan more than a /24 (256 addresses) in one call.
  * Write a single byte to a printer port. Port 9100 is connect-and-close;
    sending anything there prints it.
  * Change anything on a device. SNMP is a read-only GET.
"""

from __future__ import annotations

import concurrent.futures as _cf
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

PRINTER_PORTS = {9100: "raw", 515: "lpd", 631: "ipp"}
BRIDGE_PORT = 8420
WEB_PORTS = {80: "http", 443: "https"}
ALL_PORTS = {**PRINTER_PORTS, BRIDGE_PORT: "alphax_bridge", **WEB_PORTS}

MAX_HOSTS = 256
CONNECT_TIMEOUT = 0.35
SNMP_TIMEOUT = 0.7
WORKERS = 64

# (keyword in model text, bridge profile id). First match wins, so the more
# specific model strings sit above the vendor-only fallbacks.
_PROFILE_HINTS = [
    ("tm-m30", "epson-tm-m30"),
    ("tm-t88", "epson-tm-t88v"),
    ("tm-t20", "epson-tm-t20iii"),
    ("tsp143", "star-tsp143iii"),
    ("tsp100", "star-tsp143iii"),
    ("srp-275", "bixolon-srp-275"),
    ("ct-s310", "citizen-ct-s310"),
]
_VENDORS = ["epson", "star micronics", "star", "bixolon", "citizen", "posiflex",
            "xprinter", "rongta", "sunmi", "hp", "brother", "zebra", "canon"]


class ScanError(ValueError):
    """A request the scanner refuses. The message is shown to the operator."""


# ---------------------------------------------------------------------------
# targets
# ---------------------------------------------------------------------------


def primary_ip() -> str:
    """The address this PC uses to reach the network.

    A UDP ``connect`` only sets the socket's route; it sends no packet, so
    this works offline and triggers nothing on the network.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _allowed(ip: ipaddress.IPv4Address) -> bool:
    return ip.is_private or ip.is_link_local or ip.is_loopback


def resolve_targets(target: str | None) -> tuple[list[str], str]:
    """Turn the operator's input into a bounded list of private addresses.

    Accepts nothing (this PC's /24), a single IP, a CIDR up to /24, or a
    hostname. Returns (addresses, human description).
    """
    raw = (target or "").strip()

    if not raw:
        net = ipaddress.ip_network(f"{primary_ip()}/24", strict=False)
        if not _allowed(net.network_address):
            raise ScanError(f"This PC is on a public address ({net}). Enter the "
                            "printer's private IP or subnet explicitly.")
        hosts = [str(h) for h in net.hosts()]
        return hosts, f"local subnet {net}"

    if "/" in raw:
        try:
            net = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            raise ScanError(f"'{raw}' is not a valid network, e.g. 192.168.1.0/24")
        if net.version != 4:
            raise ScanError("Only IPv4 networks can be scanned.")
        if net.num_addresses > MAX_HOSTS:
            raise ScanError(
                f"{net} has {net.num_addresses} addresses. Scan at most a /24 "
                f"({MAX_HOSTS}) at a time.")
        if not _allowed(net.network_address):
            raise ScanError(f"{net} is a public range. Only private networks are scanned.")
        hosts = [str(h) for h in net.hosts()] or [str(net.network_address)]
        return hosts, f"network {net}"

    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(raw))
        except (OSError, ValueError):
            raise ScanError(f"Could not resolve '{raw}'.")
    if ip.version != 4:
        raise ScanError("Only IPv4 addresses can be scanned.")
    if not _allowed(ip):
        raise ScanError(f"{ip} is a public address. Only private networks are scanned.")
    return [str(ip)], f"host {ip}"


# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------


def _port_open(ip: str, port: int, timeout: float = CONNECT_TIMEOUT) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True       # connect and close; nothing is ever written
    except OSError:
        return False


def _probe_host(ip: str) -> dict | None:
    open_ports = [p for p in ALL_PORTS if _port_open(ip, p)]
    if not open_ports:
        return None
    return {"ip": ip, "ports": sorted(open_ports)}


# ---- SNMP v1 GET, hand-rolled so the bridge takes no new dependency ---------


def _ber_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x100:
        return bytes([0x81, n])
    return bytes([0x82, n >> 8, n & 0xFF])


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _ber_len(len(body)) + body


def _ber_int(v: int) -> bytes:
    b = v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big", signed=True)
    return _tlv(0x02, b)


def _oid(dotted: str) -> bytes:
    parts = [int(x) for x in dotted.split(".")]
    body = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.insert(0, 0x80 | (p & 0x7F))
            p >>= 7
        body += bytes(chunk)
    return _tlv(0x06, body)


SNMP_OIDS = {
    "1.3.6.1.2.1.1.1.0": "sys_descr",
    "1.3.6.1.2.1.1.5.0": "sys_name",
    "1.3.6.1.2.1.25.3.2.1.3.1": "device_descr",   # Host Resources MIB: printer model
}


def _snmp_request(community: str, req_id: int) -> bytes:
    binds = b"".join(_tlv(0x30, _oid(o) + b"\x05\x00") for o in SNMP_OIDS)
    pdu = _tlv(0xA0, _ber_int(req_id) + _ber_int(0) + _ber_int(0) + _tlv(0x30, binds))
    return _tlv(0x30, _ber_int(0) + _tlv(0x04, community.encode()) + pdu)


def _ber_read(buf: bytes, i: int):
    tag = buf[i]
    ln = buf[i + 1]
    i += 2
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(buf[i:i + k], "big")
        i += k
    return tag, buf[i:i + ln], i + ln


def _oid_str(body: bytes) -> str:
    out = [body[0] // 40, body[0] % 40]
    v = 0
    for b in body[1:]:
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            out.append(v)
            v = 0
    return ".".join(map(str, out))


def _walk_varbinds(buf: bytes, found: dict):
    """Collect (oid, string) pairs from anywhere in an SNMP response."""
    i = 0
    while i < len(buf):
        try:
            tag, body, nxt = _ber_read(buf, i)
        except IndexError:
            return
        if tag == 0x30 and len(body) > 2 and body[0] == 0x06:
            try:
                _, oid_b, j = _ber_read(body, 0)
                vtag, vbody, _ = _ber_read(body, j)
                if vtag == 0x04:
                    found[_oid_str(oid_b)] = vbody.decode("utf-8", "replace").strip()
            except IndexError:
                pass
        elif tag in (0x30, 0xA2):
            _walk_varbinds(body, found)
        i = nxt


def snmp_identify(ip: str, community: str = "public") -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(SNMP_TIMEOUT)
    try:
        req_id = int(time.time() * 1000) & 0x7FFFFFFF
        s.sendto(_snmp_request(community, req_id), (ip, 161))
        data, _ = s.recvfrom(4096)
    except OSError:
        return {}
    finally:
        s.close()
    found = {}
    _walk_varbinds(data, found)
    return {SNMP_OIDS[k]: v for k, v in found.items() if k in SNMP_OIDS and v}


def http_title(ip: str, port: int = 80) -> str:
    scheme = "https" if port == 443 else "http"
    try:
        import ssl
        ctx = ssl._create_unverified_context() if scheme == "https" else None
        req = urllib.request.Request(f"{scheme}://{ip}:{port}/",
                                     headers={"User-Agent": "alphax-bridge-scan"})
        with urllib.request.urlopen(req, timeout=1.2, context=ctx) as r:
            html = r.read(4096).decode("utf-8", "replace")
    except Exception:
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""


def peer_hello(ip: str, port: int = BRIDGE_PORT) -> dict:
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/hello", timeout=1.2) as r:
            data = json.loads(r.read(4096).decode("utf-8"))
        return data if isinstance(data, dict) and data.get("name") == "alphax-pos-bridge" else {}
    except Exception:
        return {}


def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# MAC addresses from the ARP table the sweep just populated
# ---------------------------------------------------------------------------

_ARP_LINE = re.compile(
    r"(\d{1,3}(?:\.\d{1,3}){3})\D+?([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})")


def arp_table() -> dict:
    out = {}
    try:
        if sys.platform.startswith("linux") and os.path.exists("/proc/net/arp"):
            with open("/proc/net/arp", encoding="utf-8") as fh:
                next(fh, None)
                for line in fh:
                    cols = line.split()
                    if len(cols) >= 4 and cols[3] != "00:00:00:00:00:00":
                        out[cols[0]] = cols[3].lower()
            return out
        cmd = ["arp", "-a"] if sys.platform.startswith("win") else ["arp", "-an"]
        flags = 0x08000000 if sys.platform.startswith("win") else 0   # CREATE_NO_WINDOW
        text = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                              creationflags=flags).stdout
        for ip, mac in _ARP_LINE.findall(text):
            out[ip] = mac.replace("-", ":").lower()
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


def _vendor(text: str) -> str:
    low = text.lower()
    for v in _VENDORS:
        if re.search(rf"\b{re.escape(v)}\b", low):
            return "Star" if v.startswith("star") else v.title() if v != "hp" else "HP"
    return ""


def _suggest_profile(text: str, is_printer: bool) -> str:
    low = text.lower()
    for key, pid in _PROFILE_HINTS:
        if key in low:
            return pid
    return "generic-network-escpos" if is_printer else ""


def classify(host: dict) -> dict:
    ports = set(host["ports"])
    ip = host["ip"]

    if BRIDGE_PORT in ports:
        hello = peer_hello(ip)
        if hello:
            host.update(kind="alphax_bridge", hostname=hello.get("hostname", ""),
                        bridge_version=hello.get("version", ""),
                        label=f"AlphaX Bridge on {hello.get('hostname') or ip}")
            return host

    is_printer = bool(ports & set(PRINTER_PORTS))
    snmp = snmp_identify(ip) if is_printer or 80 in ports else {}
    title = http_title(ip, 80) if 80 in ports else ""
    model = snmp.get("device_descr") or snmp.get("sys_descr") or title
    text = " ".join(filter(None, [model, snmp.get("sys_name", ""), title]))

    host.update(
        kind="printer" if is_printer else "device",
        model=model[:120],
        vendor=_vendor(text),
        sys_name=snmp.get("sys_name", ""),
        web_title=title,
        snmp=bool(snmp),
        protocols=[PRINTER_PORTS[p] for p in sorted(ports) if p in PRINTER_PORTS],
        suggested_profile=_suggest_profile(text, is_printer),
        print_port=9100 if 9100 in ports else (next(iter(sorted(ports & set(PRINTER_PORTS))), None)),
    )
    host["label"] = " ".join(filter(None, [host["vendor"], model or ("Network printer" if is_printer else "")])) or ip
    return host


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def scan(target: str | None = None) -> dict:
    started = time.time()
    hosts, scope = resolve_targets(target)
    me = primary_ip()

    alive = []
    with _cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for r in pool.map(_probe_host, hosts):
            if r:
                alive.append(r)

    with _cf.ThreadPoolExecutor(max_workers=16) as pool:
        found = list(pool.map(classify, alive))
        names = dict(zip([h["ip"] for h in found],
                         pool.map(reverse_dns, [h["ip"] for h in found])))

    arp = arp_table()
    for h in found:
        h["mac_address"] = arp.get(h["ip"], "")
        h["dns_name"] = names.get(h["ip"], "")
        h["is_self"] = h["ip"] == me

    order = {"printer": 0, "alphax_bridge": 1, "device": 2}
    found.sort(key=lambda h: (order.get(h["kind"], 9),
                              tuple(int(x) for x in h["ip"].split("."))))

    return {
        "scope": scope,
        "scanned": len(hosts),
        "found": len(found),
        "from_ip": me,
        "seconds": round(time.time() - started, 1),
        "devices": found,
    }
