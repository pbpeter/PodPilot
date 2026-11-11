from django.db import connection
from django.http import JsonResponse
from rest_framework import viewsets

from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer


def health(request):
    """Liveness probe - indicates if the app is running"""
    return JsonResponse({"status": "healthy"})


def ready(request):
    """Readiness probe - indicates if the app can handle requests"""
    try:
        # Check database connectivity
        connection.ensure_connection()
        return JsonResponse({"status": "ready"})
    except Exception as e:
        return JsonResponse({"status": "not ready", "error": str(e)}, status=503)
