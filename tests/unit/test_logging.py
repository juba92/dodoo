import json
import logging

from dodoo.core.logging import get_logger


def test_logger_returns_logger():
    logger = get_logger("test.module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_json_formatter_fields(capfd):
    logger = get_logger("test.json")
    logger.setLevel(logging.DEBUG)

    logger.info("hello world")
    captured = capfd.readouterr()

    # Find JSON line in output
    for line in captured.out.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        assert "timestamp" in payload
        assert "level" in payload
        assert payload["service"] == "dodoo"
        assert "correlation_id" in payload
        assert "message" in payload
        # correlation_id defaults to empty string when no request context
        assert payload["correlation_id"] == "" or isinstance(payload["correlation_id"], str)
        break
