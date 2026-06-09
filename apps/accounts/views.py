"""Account status and secure authentication views."""

from django.contrib.auth.views import LoginView
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import MFAAuthenticationForm


class SecureLoginView(LoginView):
    authentication_form = MFAAuthenticationForm
    template_name = "registration/login.html"

    def form_valid(self, form):
        self.request.session.cycle_key()
        return super().form_valid(form)


class DomainStatusView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"domain": "accounts", "status": "available"})
