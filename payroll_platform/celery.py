"""Celery application configuration."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "payroll_platform.settings.production")
app = Celery("payroll_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
