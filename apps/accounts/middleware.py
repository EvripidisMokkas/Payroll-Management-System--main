"""Idle session expiry for authenticated browser and API sessions."""

import time

from django.conf import settings
from django.contrib.auth import logout


class SessionIdleTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = int(time.time())
            last = request.session.get("last_activity", now)
            if now - last > settings.SESSION_IDLE_TIMEOUT:
                logout(request)
            else:
                request.session["last_activity"] = now
        return self.get_response(request)
