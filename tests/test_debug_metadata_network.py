"""Raw socket-level probe of the NASA Exoplanet Archive TAP endpoint.

The original ``tests/debug_metadata_network.py`` was a 167-line socket
diagnostic that walked 4 milestones (DNS+TLS, payload delivery, TTFB,
body stream ingestion) with a 4.0-second threshold per milestone and a
1 MB "accidental composite table dump" guard. Bucket 5 converts it to
a single pytest function with explicit assertions.

The 4-second per-milestone budget and the 1 MB payload-size guard are
preserved as actual ``assert`` statements. The probe targets
``WASP-12 b`` (a real Kepler planet) so that the query returns a
non-empty CSV.

This test hits the network and is marked ``@pytest.mark.network``.
It is not marked ``@slow`` because a healthy network round-trip is
typically sub-10s.
"""
from __future__ import annotations

import socket
import ssl
import time
from urllib.parse import urlencode

import pytest


_HOST = "exoplanetarchive.ipac.caltech.edu"
_PORT = 443
_PATH = "/TAP/sync"
_TARGET = "WASP-12 b"
_PER_MILESTONE_BUDGET = 4.0  # seconds
_PAYLOAD_SIZE_LIMIT = 1_000_000  # bytes (1 MB)


@pytest.mark.network
def test_nasa_tap_endpoint_responds_under_budget():
    """Raw socket probe of NASA TAP endpoint: WASP-12 b CSV under 4s/milestone,
    payload < 1 MB, body decodes as a non-empty CSV with at least one data row.
    """
    select_cols = (
        "pl_name, pl_orbper, pl_orbpererr1, st_rad, st_raderr1, st_lum, "
        "st_teff, st_mass, sy_jmag, pl_trandep, pl_ratror"
    )
    query = f"SELECT {select_cols} FROM pscomppars WHERE pl_name = '{_TARGET}'"
    params = {"query": query, "format": "csv"}
    encoded_params = urlencode(params)

    # Milestone 1: DNS + TLS connect.
    t0 = time.perf_counter()
    ip = socket.gethostbyname(_HOST)
    sock = socket.create_connection((ip, _PORT), timeout=_PER_MILESTONE_BUDGET)
    context = ssl.create_default_context()
    ssock = context.wrap_socket(sock, server_hostname=_HOST)
    ssock.settimeout(_PER_MILESTONE_BUDGET)
    ms1_time = time.perf_counter() - t0
    assert ms1_time < _PER_MILESTONE_BUDGET, (
        f"Milestone 1 (DNS+TLS) took {ms1_time:.4f}s, budget {_PER_MILESTONE_BUDGET}s"
    )

    # Milestone 2: HTTP POST payload delivery.
    request_str = (
        f"POST {_PATH} HTTP/1.1\r\n"
        f"Host: {_HOST}\r\n"
        f"Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(encoded_params)}\r\n"
        f"Connection: close\r\n\r\n"
        f"{encoded_params}"
    )
    t2_start = time.perf_counter()
    ssock.sendall(request_str.encode("utf-8"))
    ms2_time = time.perf_counter() - t2_start
    assert ms2_time < _PER_MILESTONE_BUDGET, (
        f"Milestone 2 (payload delivery) took {ms2_time:.4f}s, budget {_PER_MILESTONE_BUDGET}s"
    )

    # Milestone 3: TTFB.
    t3_start = time.perf_counter()
    first_byte = ssock.recv(1)
    assert first_byte, "Connection closed before first byte"
    ms3_time = time.perf_counter() - t3_start
    assert ms3_time < _PER_MILESTONE_BUDGET, (
        f"Milestone 3 (TTFB) took {ms3_time:.4f}s, budget {_PER_MILESTONE_BUDGET}s"
    )

    # Milestone 4: body stream ingestion.
    t4_start = time.perf_counter()
    chunks = [first_byte]
    while True:
        chunk = ssock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        elapsed = time.perf_counter() - t4_start
        assert elapsed < _PER_MILESTONE_BUDGET, (
            f"Milestone 4 (body stream) exceeded {_PER_MILESTONE_BUDGET}s "
            f"after {len(chunks)} chunks"
        )
    ms4_time = time.perf_counter() - t4_start
    full_data = b"".join(chunks)
    payload_size = len(full_data)

    # 1 MB payload-size guard: a healthy targeted TAP query should not
    # return a multi-megabyte composite table dump.
    assert payload_size < _PAYLOAD_SIZE_LIMIT, (
        f"Accidental multi-megabyte composite table download: "
        f"{payload_size} bytes (limit {_PAYLOAD_SIZE_LIMIT})"
    )

    # Body must decode and contain at least one CSV line (header + row).
    header_end = full_data.find(b"\r\n\r\n") + 4
    if header_end < 4:
        header_end = full_data.find(b"\n\n") + 2
    body = full_data[header_end:].decode("utf-8", errors="replace")
    lines = [ln for ln in body.strip().split("\n") if ln]
    assert len(lines) >= 2, (
        f"Expected at least header + 1 data row, got {len(lines)} lines"
    )
