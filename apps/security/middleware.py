"""Production HTTP hardening and bounded per-client request throttling."""

import hashlib
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=(), payment=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        return response


class RateLimitMiddleware:
    """Fixed-window throttling suitable for a shared Django cache in production."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.RATE_LIMIT_ENABLED:
            return self.get_response(request)
        identity = request.META.get("REMOTE_ADDR", "unknown")
        scope = (
            "auth"
            if request.path.startswith(("/api/v1/accounts/login/", "/api/v1/accounts/password-reset/"))
            else "api"
        )
        limit = settings.AUTH_RATE_LIMIT if scope == "auth" else settings.API_RATE_LIMIT
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        bucket = int(time.time() // window)
        digest = hashlib.sha256(f"{scope}:{identity}:{bucket}".encode()).hexdigest()
        key = f"rate-limit:{digest}"
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window + 1)
            count = 1
        if count > limit:
            response = JsonResponse({"detail": "Request rate limit exceeded."}, status=429)
            response.headers["Retry-After"] = str(window)
            return response
        return self.get_response(request)
