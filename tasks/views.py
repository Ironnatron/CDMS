import logging

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import TaskForm
from .models import Task

logger = logging.getLogger(__name__)


class SignUpView(SuccessMessageMixin, CreateView):
    form_class = UserCreationForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")
    success_message = "Your account is ready. Please log in."


class OwnedTaskMixin(LoginRequiredMixin):
    model = Task

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


class TaskListView(OwnedTaskMixin, ListView):
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 10


class TaskDetailView(OwnedTaskMixin, DetailView):
    template_name = "tasks/task_detail.html"
    context_object_name = "task"


class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_message = "Task created."

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class TaskUpdateView(OwnedTaskMixin, SuccessMessageMixin, UpdateView):
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_message = "Task updated."


class TaskDeleteView(OwnedTaskMixin, SuccessMessageMixin, DeleteView):
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("tasks:list")
    success_message = "Task deleted."


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Database health check failed.")
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
