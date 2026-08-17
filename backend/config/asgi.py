"""ASGI config. `uvicorn config.asgi:application` is the only run command — see
BASE-DESIGN.md §3: Django 6 on ASGI, served by Uvicorn, not Gunicorn/WSGI.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
