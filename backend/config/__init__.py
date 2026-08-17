# Re-exporting the Celery app here is what makes it discoverable as `celery -A config` —
# see BASE-DESIGN.md §8.2 for the worker/beat commands that rely on this.
from config.celery import app as celery_app

__all__ = ("celery_app",)
