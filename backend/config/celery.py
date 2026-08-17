"""The Celery application, discoverable as `celery -A config worker` / `-A config beat`.

`autodiscover_tasks()` is called with no explicit package list and no `CELERY_IMPORTS`
allowlist — it walks `INSTALLED_APPS` looking for a `tasks.py` in each, which is what
lets an installed app package's own `tasks.py` get picked up automatically and keep its
natural task name (e.g. `notifications_app.tasks.cleanup`) rather than something the host
had to register by hand. See APP-DESIGN.md §1.3 and INTEGRATION-GUIDE.md §2 step 8.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
