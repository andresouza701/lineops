from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions.roles import IsAdmin


class AdminOnlyView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({"message": "This is an admin-only view."})
