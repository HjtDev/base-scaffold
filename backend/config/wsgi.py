"""WSGI config. Present because BASE-DESIGN.md §2's tree lists it, but no run command in this
scaffold uses it — see BASE-DESIGN.md §3: Django 6 on ASGI, served by Uvicorn, not WSGI/Gunicorn.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
