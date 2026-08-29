"""Environment-split logging config — the request-ID contextvar/middleware/filter that used
to live here moved to `appkit.request_id` in the appkit v1.0.0 integration (BASE-DESIGN.md
§3): the envelope `appkit.exceptions.standard_exception_handler` produces carries
`request_id`, and any app logging from its own `services.py` has to stamp the same
correlation ID this host's views use, which only works if every consumer imports the same
`ContextVar` object. `MIDDLEWARE` in `config/settings.py` now lists
`appkit.request_id.RequestIDMiddleware` directly.

`build_logging_config(debug=DEBUG)` stays here — rendering (colored console in dev,
structlog JSON otherwise) is host policy, not something a shared app package has any
business deciding. See BASE-DESIGN.md §3: JSON in dev is unreadable to a person, colored
text in prod is unparseable by any log aggregator, so a single config is wrong in one
environment no matter which is picked.
"""

from typing import Any

import structlog
from appkit.request_id import RequestIDFilter, request_id_var


def _add_request_id(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: stamps the contextvar's request ID into every event dict, so it
    ends up as a real field in the JSON renderer's output and a visible key in the console
    renderer's output — for both structlog-native calls and stdlib logging calls routed
    through structlog (Django's/Celery's own `logging.getLogger(...)` calls).
    """
    event_dict["request_id"] = request_id_var.get()
    return event_dict


def build_logging_config(*, debug: bool) -> dict[str, Any]:
    """Colored console config when `debug`, structlog JSON config otherwise. Both carry
    `request_id` so a single request's log lines can be correlated — see BASE-DESIGN.md §3.
    """
    shared_processors: list[Any] = [
        _add_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Global, one-time structlog configuration — routes structlog-native log calls through
    # the same stdlib handlers/formatters as everything else, so `LOGGING` below is the one
    # source of truth for where logs actually go.
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.dev.ConsoleRenderer(colors=True) if debug else structlog.processors.JSONRenderer()
    )

    formatter = {
        "()": structlog.stdlib.ProcessorFormatter,
        "processors": [structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        "foreign_pre_chain": shared_processors,
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": RequestIDFilter},
        },
        "formatters": {
            "default": formatter,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "filters": ["request_id"],
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console"],
                "level": "INFO" if debug else "WARNING",
                "propagate": False,
            },
            "celery": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
