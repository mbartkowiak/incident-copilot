"""One JSON object per line on a dedicated logger, so CloudWatch Logs Insights discovers the
fields automatically (e.g. `stats avg(cost_usd) by bin(1d)`)."""

import json
import logging
import sys
from typing import Any

_logger = logging.getLogger("incident_copilot.telemetry")
_logger.setLevel(logging.INFO)
_logger.propagate = False
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)


def emit(event: str, **fields: Any) -> None:
    _logger.info(json.dumps({"event": event, **fields}, default=str))
