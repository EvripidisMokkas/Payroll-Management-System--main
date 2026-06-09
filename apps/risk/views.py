"""API views for the risk domain."""

from rest_framework.response import Response
from rest_framework.views import APIView


class DomainStatusView(APIView):
    """Confirm that the risk API domain is available."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"domain": "risk", "status": "available"})
