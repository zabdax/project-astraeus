"""Smoke test — proves the conftest fixtures wire up correctly."""
from astraeus.core.clients._net import HttpResponse


def test_fixtures_wire(fake_http, fake_fs, fake_clock, fake_search_result):
    assert fake_http.calls == []
    assert fake_fs.files == {}
    assert fake_clock.now() == 0.0
    assert len(fake_search_result) == 2
    # And the seam module is importable from production code. HttpResponse
    # is a `@dataclass`, so its fields live in `__dataclass_fields__` rather
    # than as direct class attributes.
    field_names = set(HttpResponse.__dataclass_fields__.keys())
    assert {"status_code", "headers", "body", "iter_chunks"}.issubset(field_names)
