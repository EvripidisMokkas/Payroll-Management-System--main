"""API views for the organizations domain."""

from rest_framework.response import Response
from rest_framework.views import APIView


class DomainStatusView(APIView):
    """Confirm that the organizations API domain is available."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"domain": "organizations", "status": "available"})
