"""Avilys's own web requests (the update check, the country database).

With "Use only this network adapter" chosen, these must not go out any other
way either: a VPN that drops would otherwise let them reveal the real
address. They are bound to the adapter's address; if it isn't connected,
the request fails instead of taking the default route."""

from __future__ import annotations

import functools
import http.client
import urllib.request


class AdapterNotConnected(OSError):
    """The chosen network adapter has no address right now."""


def urlopen(req, timeout: float, source_address: str | None = None):
    """urllib.request.urlopen, sending from `source_address` when given."""
    if not source_address:
        return urllib.request.urlopen(req, timeout=timeout)
    src = (source_address, 0)

    class BoundHTTP(urllib.request.HTTPHandler):
        def http_open(self, r):
            return self.do_open(functools.partial(http.client.HTTPConnection, source_address=src), r)

    class BoundHTTPS(urllib.request.HTTPSHandler):
        def https_open(self, r):
            return self.do_open(functools.partial(http.client.HTTPSConnection, source_address=src), r,
                                context=self._context)

    # Subclasses replace urllib's default handlers for those schemes
    return urllib.request.build_opener(BoundHTTP, BoundHTTPS).open(req, timeout=timeout)
