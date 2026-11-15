import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.cache import patch_cache_control
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import CreateView, DeleteView, DetailView, ListView

from .forms import DocumentForm, RoleForm, SuperadminSetupForm
from .models import Document, DocumentRole, DocumentSetup

logger = logging.getLogger(__name__)


@method_decorator(never_cache, name="dispatch")
class DocumentAccessMixin(LoginRequiredMixin):
    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not settings.SYNTHETIC_DOCUMENTS_ENABLED:
            raise Http404("Document prototype is disabled.")
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        role = DocumentRole.objects.filter(user=request.user).values_list(
            "role", flat=True
        ).first()
        if role not in self.allowed_roles:
            raise PermissionDenied("Your account does not have the required document role.")
        self.document_role = role
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["document_role"] = self.document_role
        return context


READ_ROLES = tuple(DocumentRole.Role.values)
WRITE_ROLES = (
    DocumentRole.Role.SUPERADMIN,
    DocumentRole.Role.ADMINISTRATOR,
    DocumentRole.Role.CLINICIAN,
)
ADMIN_ROLES = (DocumentRole.Role.SUPERADMIN, DocumentRole.Role.ADMINISTRATOR)
SUPERADMIN_ROLES = (DocumentRole.Role.SUPERADMIN,)


@method_decorator(never_cache, name="dispatch")
class SuperadminSetupView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not settings.SYNTHETIC_DOCUMENTS_ENABLED:
            raise Http404("Document prototype is disabled.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return self.render_page(request, SuperadminSetupForm())

    def post(self, request):
        if DocumentSetup.objects.filter(pk=1).exists():
            return self.render_page(request, SuperadminSetupForm())
        form = SuperadminSetupForm(request.POST)
        token = settings.DOCUMENT_SUPERADMIN_SETUP_TOKEN
        if form.is_valid():
            if not 43 <= len(token) <= 256 or not constant_time_compare(
                form.cleaned_data["setup_token"], token
            ):
                form.add_error("setup_token", "Invalid or unavailable setup secret.")
            else:
                try:
                    with transaction.atomic():
                        DocumentSetup.objects.create(pk=1, user=request.user)
                        DocumentRole.objects.update_or_create(
                            user=request.user,
                            defaults={"role": DocumentRole.Role.SUPERADMIN},
                        )
                except IntegrityError:
                    if DocumentSetup.objects.filter(pk=1).exists():
                        logger.warning("Document superadmin setup was already completed.")
                        return self.render_page(request, SuperadminSetupForm())
                    raise
                logger.info("Document superadmin initialized for user ID %s.", request.user.pk)
                messages.success(request, "Document superadmin setup completed.")
                return redirect("documents:roles")
        return self.render_page(request, form)

    def render_page(self, request, form):
        completed = DocumentSetup.objects.filter(pk=1).exists()
        if completed:
            return render(request, "documents/setup.html", {"completed": True})
        token_configured = 43 <= len(settings.DOCUMENT_SUPERADMIN_SETUP_TOKEN) <= 256
        return render(
            request,
            "documents/setup.html",
            {"form": form, "token_configured": token_configured},
            status=200 if token_configured else 503,
        )


class DocumentListView(DocumentAccessMixin, ListView):
    allowed_roles = READ_ROLES
    model = Document
    context_object_name = "documents"
    template_name = "documents/document_list.html"
    paginate_by = 10

    def get_queryset(self):
        return super().get_queryset().select_related("uploaded_by")


class DocumentDetailView(DocumentAccessMixin, DetailView):
    allowed_roles = READ_ROLES
    model = Document
    context_object_name = "document"
    template_name = "documents/document_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related("uploaded_by")


class DocumentCreateView(DocumentAccessMixin, CreateView):
    allowed_roles = WRITE_ROLES
    model = Document
    form_class = DocumentForm
    template_name = "documents/document_form.html"

    def form_valid(self, form):
        document = form.save(commit=False)
        document.uploaded_by = self.request.user
        document.original_name = Path(form.cleaned_data["file"].name).name
        try:
            document.save()
        except DatabaseError:
            if document.file and document.file._committed:
                try:
                    document.file.delete(save=False)
                except OSError:
                    logger.exception("Could not clean up a file after a database error.")
            raise
        self.object = document
        messages.success(self.request, "Synthetic document uploaded.")
        return redirect(document)


class DocumentDownloadView(DocumentAccessMixin, View):
    allowed_roles = READ_ROLES

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        try:
            file = document.file.open("rb")
        except FileNotFoundError:
            logger.warning("Document file is missing for document %s.", document.pk)
            messages.error(
                request,
                "This file is unavailable. Temporary storage may have been cleared.",
            )
            return redirect(document)
        response = FileResponse(
            file,
            as_attachment=True,
            filename=document.original_name,
            content_type="application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        patch_cache_control(response, private=True, no_store=True)
        return response


class DocumentDeleteView(DocumentAccessMixin, DeleteView):
    allowed_roles = ADMIN_ROLES
    http_method_names = ["get", "post", "head", "options"]
    model = Document
    template_name = "documents/document_confirm_delete.html"
    success_url = reverse_lazy("documents:list")

    def form_valid(self, form):
        document = self.object
        document.file.delete(save=False)
        document.delete()
        messages.success(self.request, "Synthetic document deleted.")
        return redirect(self.success_url)


class RoleListView(DocumentAccessMixin, View):
    allowed_roles = SUPERADMIN_ROLES

    def get(self, request):
        return self.render_page(request, RoleForm())

    def post(self, request):
        form = RoleForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data["username"]
            role = form.cleaned_data["role"]
            if user == request.user:
                form.add_error("role", "You cannot change your own superadmin role.")
            else:
                DocumentRole.objects.update_or_create(user=user, defaults={"role": role})
                messages.success(request, "Document role updated.")
                return redirect("documents:roles")
        return self.render_page(request, form)

    def render_page(self, request, form):
        roles = DocumentRole.objects.select_related("user").order_by("user__username")
        return render(
            request,
            "documents/role_list.html",
            {"form": form, "roles": roles, "document_role": self.document_role},
        )


class RoleRemoveView(DocumentAccessMixin, View):
    allowed_roles = SUPERADMIN_ROLES

    def post(self, request, pk):
        role = get_object_or_404(DocumentRole, pk=pk)
        if role.user_id == request.user.pk:
            messages.error(request, "You cannot remove your own superadmin role.")
        else:
            role.delete()
            messages.success(request, "Document access removed.")
        return redirect("documents:roles")
