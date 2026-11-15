from django.urls import path

from .views import (
    DocumentCreateView,
    DocumentDeleteView,
    DocumentDetailView,
    DocumentDownloadView,
    DocumentListView,
    RoleListView,
    RoleRemoveView,
    SuperadminSetupView,
)

app_name = "documents"
urlpatterns = [
    path("", DocumentListView.as_view(), name="list"),
    path("new/", DocumentCreateView.as_view(), name="create"),
    path("setup/", SuperadminSetupView.as_view(), name="setup"),
    path("roles/", RoleListView.as_view(), name="roles"),
    path("roles/<int:pk>/remove/", RoleRemoveView.as_view(), name="remove_role"),
    path("<int:pk>/", DocumentDetailView.as_view(), name="detail"),
    path("<int:pk>/download/", DocumentDownloadView.as_view(), name="download"),
    path("<int:pk>/delete/", DocumentDeleteView.as_view(), name="delete"),
]
