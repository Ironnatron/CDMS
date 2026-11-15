from django.urls import path

from .views import (
    TaskCreateView,
    TaskDeleteView,
    TaskDetailView,
    TaskListView,
    TaskUpdateView,
)

app_name = "tasks"
urlpatterns = [
    path("", TaskListView.as_view(), name="list"),
    path("tasks/new/", TaskCreateView.as_view(), name="create"),
    path("tasks/<int:pk>/", TaskDetailView.as_view(), name="detail"),
    path("tasks/<int:pk>/edit/", TaskUpdateView.as_view(), name="update"),
    path("tasks/<int:pk>/delete/", TaskDeleteView.as_view(), name="delete"),
]
