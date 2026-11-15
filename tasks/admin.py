from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "status", "due_date", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title", "owner__username"]
    readonly_fields = ["created_at", "updated_at"]
