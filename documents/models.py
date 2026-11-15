import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.urls import reverse
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateDocumentStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=settings.PRIVATE_DOCUMENT_ROOT,
            base_url=None,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
        )

    def url(self, name):
        raise ValueError("Private documents do not have public URLs.")


def document_path(instance, filename):
    return f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class DocumentRole(models.Model):
    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrator"
        CLINICIAN = "clinician", "Clinician"
        VIEWER = "viewer", "Viewer"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_role",
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f"{self.user} - {self.get_role_display()}"


class Document(models.Model):
    title = models.CharField(max_length=200)
    original_name = models.CharField(max_length=255)
    file = models.FileField(storage=PrivateDocumentStorage(), upload_to=document_path)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-pk"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("documents:detail", kwargs={"pk": self.pk})
