"""Network guard: makes 'runs offline' a property you can demonstrate, not just a promise.

Once install() is called, this Python process cannot open an outbound network
connection or resolve a hostname. Only loopback (this computer talking to itself)
is allowed, which the local web page needs. Every refused attempt is counted.

Honest scope: this guards the SemanticEye process itself. It does not replace
an operating-system firewall, and switching Wi-Fi off gives the same result.
"""
import socket
import threading

_state = threading.local()
_lock = threading.Lock()
_blocked = 0
_installed = False
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "", None}


class NetworkBlocked(OSError):
    pass


def _host_of(addr):
    if isinstance(addr, tuple) and addr:
        return addr[0]
    return addr


def _is_local(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host in _LOCAL_NAMES:
        return True
    return isinstance(host, str) and (host.startswith("127.") or host == "::1")


def _refuse(what: str):
    global _blocked
    if not getattr(_state, "probing", False):
        with _lock:
            _blocked += 1
    raise NetworkBlocked(f"SemanticEye network guard blocked: {what}")


def install():
    global _installed
    if _installed:
        return
    _installed = True
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    orig_sendto = socket.socket.sendto
    orig_getaddrinfo = socket.getaddrinfo
    orig_gethostbyname = socket.gethostbyname

    def connect(self, addr):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(_host_of(addr)):
            _refuse("outbound connection")
        return orig_connect(self, addr)

    def connect_ex(self, addr):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(_host_of(addr)):
            _refuse("outbound connection")
        return orig_connect_ex(self, addr)

    def sendto(self, data, *args):
        if self.family in (socket.AF_INET, socket.AF_INET6) and args and not _is_local(_host_of(args[-1])):
            _refuse("outbound datagram")
        return orig_sendto(self, data, *args)

    def getaddrinfo(host, *a, **k):
        if not _is_local(host):
            _refuse("name lookup")
        return orig_getaddrinfo(host, *a, **k)

    def gethostbyname(host):
        if not _is_local(host):
            _refuse("name lookup")
        return orig_gethostbyname(host)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname


def blocked_count() -> int:
    return _blocked


def probe() -> dict:
    """Live self-test: really try to reach the outside world and report what happened.
    Probe attempts are not added to the real counter."""
    results = []
    _state.probing = True
    try:
        for label, fn in (
            ("connect to 8.8.8.8:53", lambda: socket.create_connection(("8.8.8.8", 53), timeout=1)),
            ("resolve example.com", lambda: socket.getaddrinfo("example.com", 443)),
        ):
            try:
                fn()
                results.append({"test": label, "blocked": False})
            except NetworkBlocked:
                results.append({"test": label, "blocked": True})
            except OSError:
                # no route / no internet: nothing left the machine either way
                results.append({"test": label, "blocked": True, "note": "unreachable"})
    finally:
        _state.probing = False
    return {"guard_active": _installed, "tests": results,
            "all_blocked": all(r["blocked"] for r in results),
            "real_attempts_blocked": _blocked}
