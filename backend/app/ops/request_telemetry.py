"""Opt-in, content-free ASGI telemetry. This is not the business audit ledger."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from collections.abc import Callable, Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

METHODS = frozenset({'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT'})
LOGGER_NAME = 'slc.request_telemetry'


def json_log_sink(record: dict) -> None:
    # Use only our own logger. Do not reconfigure Uvicorn, handlers or root logging.
    logger = logging.getLogger(LOGGER_NAME)
    logger.info(json.dumps(record, separators=(',', ':'), allow_nan=False))


def configure_json_logger() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestTelemetryMiddleware:
    """One fixed-size record per HTTP invocation; no bodies or incoming IDs read.

    Route labels are snapshotted from registered templates, never scope['path'].
    Guard rejection before routing and unknown routes share '__unmatched__'.
    No global counters, URL cardinality, network requests or persistent storage.
    """

    def __init__(self, app: ASGIApp, *, enabled: bool = False,
                 route_templates: Iterable[str] = (),
                 sink: Callable[[dict], None] | None = None):
        self.app = app
        self.enabled = enabled
        self.templates = frozenset(route_templates)
        self.sink = sink if sink is not None else json_log_sink
        if enabled and sink is None:
            configure_json_logger()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        timestamp_ms = time.time_ns() // 1_000_000
        status_code = 0
        completed = False
        disconnected = False
        outcome = 'incomplete'

        async def observed_receive() -> Message:
            nonlocal disconnected
            message = await receive()
            if message['type'] == 'http.disconnect':
                disconnected = True
            return message

        async def observed_send(message: Message) -> None:
            nonlocal status_code, completed
            await send(message)  # Do not mark delivery successful before send returns.
            if message['type'] == 'http.response.start':
                status_code = message['status']
            elif message['type'] == 'http.response.body' and not message.get('more_body', False):
                completed = True

        try:
            await self.app(scope, observed_receive, observed_send)
            outcome = 'complete' if completed else ('disconnected' if disconnected else 'incomplete')
        except asyncio.CancelledError:
            outcome = 'cancelled'
            raise
        except BaseException:
            outcome = 'error'
            raise
        finally:
            # Exception text, principal, body, query, raw path, headers and peer IP
            # are deliberately never copied, including malformed/unmatched input.
            template = getattr(scope.get('route'), 'path', None)
            route = template if template in self.templates else '__unmatched__'
            method = scope.get('method')
            record = {
                'schema_version': 1, 'event': 'http_request',
                'timestamp_ms': timestamp_ms, 'request_id': uuid.uuid4().hex,
                'method': method if method in METHODS else 'OTHER', 'route': route,
                'status': status_code, 'outcome': outcome,
                'duration_ms': round(max(0.0, time.perf_counter() - started) * 1000, 3),
            }
            try:
                self.sink(record)
            except Exception:
                # Telemetry failures must not change a response or replace an
                # original exception. No fallback with potentially sensitive text.
                pass
