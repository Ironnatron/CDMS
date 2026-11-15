import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import MAX_DOCUMENT_SIZE
from .models import Document, DocumentRole, DocumentSetup

User = get_user_model()


@override_settings(SYNTHETIC_DOCUMENTS_ENABLED=True)
class DocumentPrototypeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("docadmin")
        cls.superadmin = User.objects.create_user("docsuperadmin")
        cls.clinician = User.objects.create_user("clinician")
        cls.viewer = User.objects.create_user("viewer")
        cls.outsider = User.objects.create_user("outsider")
        for user, role in [
            (cls.superadmin, DocumentRole.Role.SUPERADMIN),
            (cls.admin, DocumentRole.Role.ADMINISTRATOR),
            (cls.clinician, DocumentRole.Role.CLINICIAN),
            (cls.viewer, DocumentRole.Role.VIEWER),
        ]:
            DocumentRole.objects.create(user=user, role=role)
        DocumentSetup.objects.create(user=cls.superadmin)

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        patcher = patch.object(
            Document._meta.get_field("file"),
            "storage",
            FileSystemStorage(location=self.tempdir.name),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def create_document(self, title="Synthetic file", content=b"fictional"):
        document = Document(title=title, original_name="sample.txt", uploaded_by=self.clinician)
        document.file.save("sample.txt", ContentFile(content), save=True)
        return document

    def test_feature_disabled_blocks_every_route_even_for_admin(self):
        document = self.create_document()
        role = self.viewer.document_role
        self.client.force_login(self.admin)
        routes = [
            ("list", []),
            ("create", []),
            ("detail", [document.pk]),
            ("download", [document.pk]),
            ("delete", [document.pk]),
            ("roles", []),
            ("remove_role", [role.pk]),
            ("setup", []),
        ]
        with override_settings(SYNTHETIC_DOCUMENTS_ENABLED=False):
            for name, args in routes:
                url = reverse(f"documents:{name}", args=args)
                for method in [self.client.get, self.client.post]:
                    with self.subTest(name=name, method=method.__name__):
                        self.assertEqual(method(url).status_code, 404)
            self.assertNotContains(self.client.get(reverse("tasks:list")), "Documents")
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        self.assertTrue(DocumentRole.objects.filter(pk=role.pk).exists())

    def test_anonymous_redirects_and_unassigned_user_is_denied(self):
        document = self.create_document()
        role = self.viewer.document_role
        routes = [
            ("list", []),
            ("create", []),
            ("detail", [document.pk]),
            ("download", [document.pk]),
            ("delete", [document.pk]),
            ("roles", []),
            ("remove_role", [role.pk]),
        ]
        for name, args in routes:
            url = reverse(f"documents:{name}", args=args)
            with self.subTest(name=name, user="anonymous"):
                self.assertEqual(self.client.get(url).status_code, 302)
                self.assertEqual(self.client.post(url).status_code, 302)
        self.client.force_login(self.outsider)
        for name, args in routes:
            url = reverse(f"documents:{name}", args=args)
            for method in [self.client.get, self.client.post]:
                with self.subTest(name=name, method=method.__name__):
                    self.assertEqual(method(url).status_code, 403)

    def test_role_permissions_and_direct_requests(self):
        document = self.create_document()
        other_role = self.viewer.document_role
        for user in [self.superadmin, self.admin, self.clinician, self.viewer]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("documents:list")).status_code, 200)
            self.assertEqual(self.client.get(document.get_absolute_url()).status_code, 200)
            response = self.client.get(reverse("documents:download", args=[document.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"fictional")
            response.close()
            is_admin = user in (self.superadmin, self.admin)
            is_superadmin = user == self.superadmin
            can_upload = user != self.viewer
            for name, args, allowed in [
                ("create", [], can_upload),
                ("delete", [document.pk], is_admin),
                ("roles", [], is_superadmin),
            ]:
                with self.subTest(user=user.username, route=name):
                    self.assertEqual(
                        self.client.get(reverse(f"documents:{name}", args=args)).status_code,
                        200 if allowed else 403,
                    )
            if not is_admin:
                self.assertEqual(
                    self.client.post(reverse("documents:delete", args=[document.pk])).status_code,
                    403,
                )
            if not is_superadmin:
                self.assertEqual(
                    self.client.post(reverse("documents:remove_role", args=[other_role.pk])).status_code,
                    403,
                )
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        self.assertTrue(DocumentRole.objects.filter(pk=other_role.pk).exists())

    def test_clinician_upload_viewer_download_and_private_storage(self):
        self.client.force_login(self.clinician)
        uploaded = SimpleUploadedFile("fiction.txt", b"Fictional test data")
        response = self.client.post(
            reverse("documents:create"),
            {"title": "Synthetic report", "file": uploaded, "uploaded_by": self.admin.pk},
        )
        document = Document.objects.get()
        self.assertRedirects(response, document.get_absolute_url())
        self.assertEqual(document.uploaded_by, self.clinician)
        self.assertNotEqual(document.file.name, document.original_name)
        self.assertEqual(document.original_name, "fiction.txt")
        self.assertTrue(Path(document.file.path).exists())
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("documents:download", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"Fictional test data")
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        response.close()
        self.assertEqual(self.client.get(f"/private_documents/{document.file.name}").status_code, 404)

    def test_private_storage_does_not_expose_a_url(self):
        from .models import PrivateDocumentStorage

        with self.assertRaises(ValueError):
            PrivateDocumentStorage().url("example.txt")

    def test_invalid_uploads_are_rejected_without_writing(self):
        self.client.force_login(self.clinician)
        cases = [
            ("bad.exe", b"bad"),
            ("empty.txt", b""),
            ("too-large.pdf", b"x" * (MAX_DOCUMENT_SIZE + 1)),
        ]
        for name, content in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    reverse("documents:create"),
                    {"title": "Synthetic", "file": SimpleUploadedFile(name, content)},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("file", response.context["form"].errors)
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(list(Path(self.tempdir.name).iterdir()), [])

    def test_missing_file_reports_unavailability_and_keeps_metadata(self):
        document = self.create_document()
        document.file.delete(save=False)
        self.client.force_login(self.viewer)
        with self.assertLogs("documents.views", level="WARNING"):
            response = self.client.get(reverse("documents:download", args=[document.pk]), follow=True)
        self.assertRedirects(response, document.get_absolute_url())
        self.assertContains(response, "This file is unavailable.")
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())

    def test_admin_delete_requires_post_and_removes_file_and_record(self):
        document = self.create_document()
        file_path = Path(document.file.path)
        self.client.force_login(self.admin)
        url = reverse("documents:delete", args=[document.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(file_path.exists())
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertTrue(file_path.exists())
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        response = self.client.post(url, follow=True)
        self.assertRedirects(response, reverse("documents:list"))
        self.assertContains(response, "Synthetic document deleted.")
        self.assertFalse(file_path.exists())
        self.assertFalse(Document.objects.filter(pk=document.pk).exists())

    def test_superadmin_assigns_updates_and_removes_access(self):
        self.client.force_login(self.superadmin)
        url = reverse("documents:roles")
        response = self.client.post(url, {"username": "outsider", "role": "viewer"})
        self.assertRedirects(response, url)
        self.assertEqual(self.outsider.document_role.role, DocumentRole.Role.VIEWER)
        self.client.post(url, {"username": "outsider", "role": "clinician"})
        role = DocumentRole.objects.get(user=self.outsider)
        self.assertEqual(role.role, DocumentRole.Role.CLINICIAN)
        self.assertEqual(self.client.get(reverse("documents:remove_role", args=[role.pk])).status_code, 405)
        response = self.client.post(reverse("documents:remove_role", args=[role.pk]))
        self.assertRedirects(response, url)
        self.assertFalse(DocumentRole.objects.filter(pk=role.pk).exists())
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("documents:list")).status_code, 403)

    def test_superadmin_cannot_revoke_or_change_own_role(self):
        self.client.force_login(self.superadmin)
        response = self.client.post(
            reverse("documents:roles"), {"username": "docsuperadmin", "role": "viewer"}
        )
        self.assertContains(response, "You cannot change your own superadmin role.")
        response = self.client.post(
            reverse("documents:remove_role", args=[self.superadmin.document_role.pk]), follow=True
        )
        self.assertContains(response, "You cannot remove your own superadmin role.")
        self.assertEqual(DocumentRole.objects.get(user=self.superadmin).role, "superadmin")

    def test_invalid_or_inactive_role_assignment_is_rejected(self):
        self.client.force_login(self.superadmin)
        self.outsider.is_active = False
        self.outsider.save()
        for data in [
            {"username": "not-a-user", "role": "viewer"},
            {"username": "outsider", "role": "viewer"},
            {"username": "viewer", "role": "invalid"},
            {"username": "viewer", "role": "superadmin"},
        ]:
            response = self.client.post(reverse("documents:roles"), data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(DocumentRole.objects.count(), 4)

    def test_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.superadmin)
        document = self.create_document()
        for name, args in [
            ("create", []),
            ("delete", [document.pk]),
            ("roles", []),
            ("remove_role", [self.viewer.document_role.pk]),
        ]:
            with self.subTest(name=name):
                self.assertEqual(client.post(reverse(f"documents:{name}", args=args)).status_code, 403)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        self.assertTrue(DocumentRole.objects.filter(user=self.viewer).exists())

    def test_document_pages_are_not_cacheable(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("documents:list"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(response, "Synthetic data only.")

    def test_existing_admin_cannot_assign_roles_or_revoke_access(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.post(
                reverse("documents:roles"),
                {"username": "outsider", "role": "administrator"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("documents:remove_role", args=[self.viewer.document_role.pk])
            ).status_code,
            403,
        )
        self.assertFalse(DocumentRole.objects.filter(user=self.outsider).exists())
        self.assertTrue(DocumentRole.objects.filter(user=self.viewer).exists())

    def test_database_rejects_second_superadmin(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentRole.objects.create(
                    user=self.outsider, role=DocumentRole.Role.SUPERADMIN
                )
        self.assertEqual(
            DocumentRole.objects.filter(role=DocumentRole.Role.SUPERADMIN).count(), 1
        )

    def test_setup_owner_cannot_be_deleted_but_other_roles_can(self):
        with self.assertRaises(ProtectedError):
            self.superadmin.delete()
        viewer_id = self.viewer.pk
        self.viewer.delete()
        self.assertFalse(DocumentRole.objects.filter(user_id=viewer_id).exists())


@override_settings(
    SYNTHETIC_DOCUMENTS_ENABLED=True,
    DOCUMENT_SUPERADMIN_SETUP_TOKEN="synthetic-setup-token-example-not-a-real-secret-123456789",
)
class SuperadminSetupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first = User.objects.create_user("first")
        cls.second = User.objects.create_user("second")
        cls.token = "synthetic-setup-token-example-not-a-real-secret-123456789"

    def test_authenticated_setup_promotes_existing_admin_and_is_one_time(self):
        DocumentRole.objects.create(user=self.first, role=DocumentRole.Role.ADMINISTRATOR)
        self.client.force_login(self.first)
        response = self.client.post(
            reverse("documents:setup"), {"setup_token": self.token}
        )
        self.assertRedirects(response, reverse("documents:roles"))
        self.assertEqual(
            DocumentRole.objects.get(user=self.first).role, DocumentRole.Role.SUPERADMIN
        )
        self.assertEqual(DocumentSetup.objects.get(pk=1).user, self.first)
        self.client.force_login(self.second)
        response = self.client.post(
            reverse("documents:setup"), {"setup_token": self.token}
        )
        self.assertContains(response, "Setup has already been completed.")
        self.assertFalse(DocumentRole.objects.filter(user=self.second).exists())
        self.assertEqual(DocumentRole.objects.filter(role="superadmin").count(), 1)

    def test_invalid_token_and_unconfigured_token_never_grant_access(self):
        self.client.force_login(self.first)
        response = self.client.post(
            reverse("documents:setup"), {"setup_token": "wrong"}
        )
        self.assertContains(response, "Invalid or unavailable setup secret.")
        self.assertFalse(DocumentSetup.objects.exists())
        for token in ["", "too-short", "x" * 257]:
            with self.subTest(token_length=len(token)):
                with override_settings(DOCUMENT_SUPERADMIN_SETUP_TOKEN=token):
                    response = self.client.post(
                        reverse("documents:setup"), {"setup_token": token}
                    )
                    self.assertEqual(response.status_code, 503)
                    self.assertFalse(DocumentSetup.objects.exists())
                    self.assertFalse(DocumentRole.objects.exists())

    def test_setup_requires_authentication_csrf_and_feature_enabled(self):
        url = reverse("documents:setup")
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(url).status_code, 302)
        client.force_login(self.first)
        self.assertEqual(client.post(url, {"setup_token": self.token}).status_code, 403)
        with override_settings(SYNTHETIC_DOCUMENTS_ENABLED=False):
            self.assertEqual(client.get(url).status_code, 404)
        client.get(url)
        response = client.post(
            url,
            {
                "setup_token": self.token,
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )
        self.assertRedirects(response, reverse("documents:roles"))

    def test_setup_secret_is_never_echoed_and_setup_page_is_not_cached(self):
        self.client.force_login(self.first)
        response = self.client.post(
            reverse("documents:setup"), {"setup_token": "incorrect-secret-value"}
        )
        self.assertNotContains(response, "incorrect-secret-value")
        self.assertNotContains(response, self.token)
        self.assertIn("no-store", response["Cache-Control"])

    def test_marker_blocks_reinitialization_even_if_role_removed_outside_app(self):
        DocumentSetup.objects.create(user=self.first)
        self.client.force_login(self.second)
        response = self.client.post(
            reverse("documents:setup"), {"setup_token": self.token}
        )
        self.assertContains(response, "Setup has already been completed.")
        self.assertFalse(DocumentRole.objects.exists())
