"""ASGI config for the payroll platform."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payroll_platform.settings.production")
application = get_asgi_application()
