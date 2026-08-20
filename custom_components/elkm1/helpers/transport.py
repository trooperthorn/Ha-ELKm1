"""Hybrid transport layer for Elk-M1: native baud-aware connect, elkm1-lib protocol.

Architecture decision (see PROJECT_MAP.md): elkm1_lib's message encode/decode
(message.py) and Elk-class orchestration (subsystem objects, handler
dispatch) are reused as-is rather than reimplemented from the protocol
manual by hand. Only the transport-opening half of elkm1_lib.connection.
Connection.connect() is replaced, so this integration controls baud
handling for serial ports while everything downstream of "we have a
reader/writer pair" - checksum, framing, the write queue, reconnect-on-
heartbeat-timeout - stays exactly elkm1-lib's own, already-correct code.

Why monkeypatching instead of subclassing: elkm1_lib.Elk.__init__()
unconditionally does `self._connection = Connection(config["url"],
notifier)` and immediately hands that instance to every subsystem object
(Areas, Zones, Outputs, ...), each of which stores its own reference at
construction time. There is no constructor seam to inject a Connection
subclass instance in its place - by the time Elk() returns, a dozen
objects already hold a reference to the *original* Connection. Subclassing
would therefore require also overriding Elk.__init__, which is a much
larger and more fragile diff against a pinned external dependency than
replacing one bound method on the Connection class itself. The patch is
applied once, idempotently, at import time.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import timeout as asyncio_timeout
from typing import Any

from elkm1_lib import Elk
from elkm1_lib.connection import Connection
from elkm1_lib.util import parse_url

from .baud_probe import BaudProbeError, open_probed_serial, probe_baud

_LOGGER = logging.getLogger(__name__)

_PATCHED_ATTR = "_elkm1ha_baud_patched"


class ConnectionTimeoutError(Exception):
    """Raised when a network/serial validation connection never confirms a live panel."""


class InvalidAuthError(Exception):
    """Raised when a secure network connection is rejected for bad credentials."""


async def _connect_with_baud_probe(self: Connection) -> None:
    """Drop-in replacement for elkm1_lib.connection.Connection.connect().

    Identical to elkm1-lib 2.2.15's implementation except that a serial://
    URL's baud rate is resolved via probe_baud() instead of assuming
    parse_url()'s single fixed value (which parse_url only returns because
    the serial:// URL scheme technically allows a `:baud` suffix that
    nothing in this integration's config flow ever sets). Network
    connections are untouched.
    """
    _LOGGER.info("Connecting to ElkM1 at %s", self._url)
    retry_time = 1
    scheme, dest, param, ssl_context = parse_url(self._url)
    cached_baud: int | None = getattr(self, "_elkm1ha_cached_baud", None)

    while not self._writer:
        try:
            async with asyncio_timeout(30):
                if scheme == "serial":
                    # open_probed_serial() leaves the winning attempt's
                    # connection open and hands it straight back, rather
                    # than closing the probe and reopening a second time.
                    baud, reader, self._writer = await open_probed_serial(
                        dest, cached_baud
                    )
                    self._elkm1ha_cached_baud = baud  # type: ignore[attr-defined]
                    cached_baud = baud
                    on_baud_detected = getattr(self, "_elkm1ha_on_baud_detected", None)
                    if on_baud_detected is not None:
                        on_baud_detected(baud)
                else:
                    reader, self._writer = await asyncio.open_connection(
                        host=dest, port=param, ssl=ssl_context
                    )
        except (TimeoutError, ValueError, OSError, BaudProbeError) as err:
            _LOGGER.warning(
                "Error connecting to ElkM1 (%s). Retrying in %d seconds", err, retry_time
            )
            await asyncio.sleep(retry_time)
            retry_time = min(60, retry_time * 2)
            continue

        if scheme != "serial":
            self._tasks.add(asyncio.create_task(self._heartbeat_timer()))
        self._tasks.add(asyncio.create_task(self._read_stream(reader)))
        self._tasks.add(asyncio.create_task(self._write_stream()))
        self._notifier.notify("connected", {})


def ensure_baud_probe_patch_applied() -> None:
    """Patch Connection.connect once per process. Safe to call repeatedly."""
    if getattr(Connection, _PATCHED_ATTR, False):
        return
    Connection.connect = _connect_with_baud_probe  # type: ignore[method-assign]
    setattr(Connection, _PATCHED_ATTR, True)


def attach_baud_state(
    elk: Elk,
    *,
    cached_baud: int | None = None,
    on_baud_detected: Any = None,
) -> None:
    """Seed a cached baud rate and/or a detected-baud callback onto elk's connection.

    Must be called after Elk(config) construction and before elk.connect().
    """
    ensure_baud_probe_patch_applied()
    connection = elk.connection
    if cached_baud is not None:
        connection._elkm1ha_cached_baud = cached_baud  # type: ignore[attr-defined]
    if on_baud_detected is not None:
        connection._elkm1ha_on_baud_detected = on_baud_detected  # type: ignore[attr-defined]


async def validate_serial_port(port: str, cached_baud: int | None = None) -> int:
    """Confirm an Elk-M1 panel responds on `port` and return its baud rate.

    Thin wrapper around probe_baud() shared by config_flow's serial setup
    step and helpers/usb_discovery.py's candidate-port probing, so there is
    one probing implementation, not two.
    """
    return await probe_baud(port, cached_baud)


async def validate_network_connection(
    url: str,
    userid: str | None = None,
    password: str | None = None,
    timeout: float = 10.0,
) -> None:
    """Confirm a live Elk-M1 panel over a network URL, raising on failure.

    Uses a short-lived real elkm1_lib.Elk instance rather than a hand-rolled
    socket so secure schemes (elks://, elksv1_2://) genuinely exercise
    elkm1-lib's TLS context and credential handshake (Connection.connect()
    picks up parse_url()'s ssl_context; Elk._connected() sends userid/
    password for secure schemes) - the socket-level validation this
    replaced skipped both entirely and could not have actually verified a
    secure connection.
    """
    ensure_baud_probe_patch_applied()
    config: dict[str, Any] = {"url": url}
    if userid is not None:
        config["userid"] = userid
    if password is not None:
        config["password"] = password

    elk = Elk(config)
    got_version = asyncio.Event()
    login_failed = asyncio.Event()

    def _on_vn(**_kwargs: Any) -> None:
        got_version.set()

    def _on_login(succeeded: bool) -> None:
        if not succeeded:
            login_failed.set()

    elk.add_handler("VN", _on_vn)
    elk.add_handler("login", _on_login)

    try:
        elk.connect()
        vn_task = asyncio.ensure_future(got_version.wait())
        login_failed_task = asyncio.ensure_future(login_failed.wait())
        try:
            async with asyncio_timeout(timeout):
                await asyncio.wait(
                    (vn_task, login_failed_task), return_when=asyncio.FIRST_COMPLETED
                )
        except TimeoutError as exc:
            raise ConnectionTimeoutError(f"No response from {url}") from exc
        finally:
            for task in (vn_task, login_failed_task):
                if not task.done():
                    task.cancel()

        if login_failed.is_set():
            raise InvalidAuthError(f"Authentication rejected by {url}")
        if not got_version.is_set():
            raise ConnectionTimeoutError(f"No response from {url}")
    finally:
        elk.disconnect()
