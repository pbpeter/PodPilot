from django.contrib import admin
from django.urls import include, path

from tasks.views import health, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("tasks.urls")),
    path("health", health),
    path("ready", ready),
]
