from django.contrib import admin

from .models import Task


# Register your models here.


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "priority",
        "assigned_to",
        "due_date",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "priority", "created_at", "due_date")
    search_fields = ("title", "description", "assigned_to__username", "assigned_to__email")
    ordering = ("-created_at",)
    list_select_related = ("assigned_to",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("title", "description")}),
        ("Workflow", {"fields": ("status", "priority", "assigned_to", "due_date")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
