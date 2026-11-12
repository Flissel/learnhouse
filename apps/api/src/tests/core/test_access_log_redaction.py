"""Tests for src/core/access_log_redaction.py (pure unit tests, no app start)."""

import logging

from src.core.access_log_redaction import (
    AccessLogRedactionFilter,
    install_access_log_redaction,
    redact_path,
)

TOKEN = "Zk3-secretTOKENvalue_123"


def _record(path: str, status: int = 200) -> logging.LogRecord:
    # uvicorn.access format: '%s - "%s %s HTTP/%s" %d'
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "GET", path, "1.1", status), None,
    )


def _render(record: logging.LogRecord) -> str:
    AccessLogRedactionFilter().filter(record)
    return record.getMessage()


def test_einladung_token_is_masked_keeping_structure():
    for suffix in ("", "/annehmen", "/konto"):
        msg = _render(_record(f"/api/v1/learning/einladung/{TOKEN}{suffix}", 201))
        assert TOKEN not in msg
        assert f"/api/v1/learning/einladung/***{suffix}" in msg
        assert msg.endswith("201")
        assert "GET" in msg and "HTTP/1.1" in msg


def test_other_token_path_segments_are_masked():
    for path in (
        f"/api/v1/media/shared/{TOKEN}/file",
        f"/api/v1/users/abc/invite/{TOKEN}",
    ):
        assert TOKEN not in _render(_record(path))


def test_sensitive_query_values_are_masked_other_params_kept():
    msg = _render(_record(f"/api/v1/admin/x/magic?token={TOKEN}&page=2&code={TOKEN}"))
    assert TOKEN not in msg
    assert "token=***" in msg and "code=***" in msg and "page=2" in msg


def test_harmless_paths_unchanged():
    for path in ("/api/v1/health", "/api/v1/courses/course_1?page=2&limit=20",
                 "/api/v1/learning/verwaltung/links"):
        assert redact_path(path) == path
        assert path in _render(_record(path))


def test_filter_never_drops_records_and_tolerates_odd_args():
    f = AccessLogRedactionFilter()
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "plain", None, None)
    assert f.filter(rec) is True
    rec2 = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%s", ("x",), None)
    assert f.filter(rec2) is True


def test_install_is_idempotent_and_hits_uvicorn_access():
    logger = logging.getLogger("uvicorn.access")
    install_access_log_redaction()
    install_access_log_redaction()
    n = [x for x in logger.filters if isinstance(x, AccessLogRedactionFilter)]
    assert len(n) == 1
