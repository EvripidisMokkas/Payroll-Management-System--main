"""Admin registration for the organization risk register."""

from django.contrib import admin

from .models import RiskRegisterEntry

admin.site.register(RiskRegisterEntry)
