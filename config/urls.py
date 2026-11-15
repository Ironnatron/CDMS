from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from tasks.views import SignUpView, health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/signup/", SignUpView.as_view(), name="signup"),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("health/", health, name="health"),
    path("documents/", include("documents.urls")),
    path("", include("tasks.urls")),
]
