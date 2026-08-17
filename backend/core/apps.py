from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        # Connects every receiver in core/signals.py at startup. Forgetting this is the
        # most common reason a signal receiver "silently doesn't fire" — see
        # INTEGRATION-GUIDE.md §4.
        import core.signals  # noqa: F401
