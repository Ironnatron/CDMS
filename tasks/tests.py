from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.html import escape

from .models import Task

User = get_user_model()


class AuthenticationTests(TestCase):
    password = "A-unique-test-passphrase-739!"

    def test_signup_creates_user_with_hashed_password_and_redirects_to_login(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newuser",
                "password1": self.password,
                "password2": self.password,
            },
        )
        self.assertRedirects(response, reverse("login"))
        user = User.objects.get(username="newuser")
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))

    def test_signup_rejects_weak_mismatched_and_duplicate_credentials(self):
        User.objects.create_user("existing")
        for username, password1, password2, error_field in [
            ("weakuser", "123", "123", "password2"),
            ("mismatch", self.password, "different", "password2"),
            ("existing", self.password, self.password, "username"),
        ]:
            with self.subTest(username=username):
                response = self.client.post(
                    reverse("signup"),
                    {
                        "username": username,
                        "password1": password1,
                        "password2": password2,
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(error_field, response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_login_rejects_bad_password_then_accepts_valid_credentials(self):
        user = User.objects.create_user("loginuser", password=self.password)
        response = self.client.post(
            reverse("login"), {"username": user.username, "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": self.password},
        )
        self.assertRedirects(response, reverse("tasks:list"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_login_preserves_local_next_and_rejects_external_redirect(self):
        user = User.objects.create_user("redirectuser", password=self.password)
        for next_url, expected in [
            (reverse("tasks:create"), reverse("tasks:create")),
            ("https://untrusted.example/", reverse("tasks:list")),
        ]:
            with self.subTest(next_url=next_url):
                self.client.logout()
                response = self.client.post(
                    reverse("login"),
                    {
                        "username": user.username,
                        "password": self.password,
                        "next": next_url,
                    },
                )
                self.assertRedirects(response, expected)

    def test_logout_requires_post_and_clears_session(self):
        user = User.objects.create_user("logoutuser")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertRedirects(
            self.client.post(reverse("logout")), reverse("login")
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_login_and_logout_require_csrf_tokens(self):
        client = Client(enforce_csrf_checks=True)
        for route in ["signup", "login", "logout"]:
            with self.subTest(route=route):
                self.assertEqual(client.post(reverse(route), {}).status_code, 403)
        response = client.get(reverse("signup"))
        token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("signup"),
            {
                "username": "csrfuser",
                "password1": self.password,
                "password2": self.password,
                "csrfmiddlewaretoken": token,
            },
        )
        self.assertRedirects(response, reverse("login"))


class TaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("owner")
        cls.other = User.objects.create_user("other")
        cls.task = Task.objects.create(owner=cls.owner, title="Owner's task")
        cls.other_task = Task.objects.create(owner=cls.other, title="Private task")

    def setUp(self):
        self.client.force_login(self.owner)

    def task_data(self, **overrides):
        data = {
            "title": "A new task",
            "description": "Some details",
            "status": Task.Status.IN_PROGRESS,
            "due_date": "2027-01-20",
        }
        data.update(overrides)
        return data

    def test_anonymous_users_cannot_read_or_mutate_tasks(self):
        self.client.logout()
        routes = [
            reverse("tasks:list"),
            reverse("tasks:create"),
            reverse("tasks:detail", args=[self.task.pk]),
            reverse("tasks:update", args=[self.task.pk]),
            reverse("tasks:delete", args=[self.task.pk]),
        ]
        for url in routes:
            for method in [self.client.get, self.client.post]:
                with self.subTest(url=url, method=method.__name__):
                    response = method(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(
                        response.url, f"{reverse('login')}?next={url}"
                    )
        self.assertEqual(Task.objects.count(), 2)

    def test_list_only_shows_owned_tasks(self):
        response = self.client.get(reverse("tasks:list"))
        self.assertContains(response, escape(self.task.title))
        self.assertNotContains(response, self.other_task.title)
        self.assertEqual(list(response.context["tasks"]), [self.task])

    def test_empty_list_offers_create_action(self):
        Task.objects.filter(owner=self.owner).delete()
        response = self.client.get(reverse("tasks:list"))
        self.assertContains(response, "Create your first task")
        self.assertNotContains(response, self.other_task.title)

    def test_list_pagination_never_includes_other_users_tasks(self):
        Task.objects.bulk_create(
            [Task(owner=self.owner, title=f"Task {index}") for index in range(10)]
        )
        first = self.client.get(reverse("tasks:list"))
        second = self.client.get(reverse("tasks:list"), {"page": 2})
        self.assertEqual(len(first.context["tasks"]), 10)
        self.assertEqual(len(second.context["tasks"]), 1)
        self.assertEqual(first.context["paginator"].count, 11)
        for response in [first, second]:
            self.assertNotContains(response, self.other_task.title)

    def test_create_sets_owner_and_ignores_submitted_owner(self):
        response = self.client.post(
            reverse("tasks:create"), self.task_data(owner=self.other.pk)
        )
        task = Task.objects.get(title="A new task")
        self.assertRedirects(response, task.get_absolute_url())
        self.assertEqual(task.owner, self.owner)
        self.assertEqual(task.description, "Some details")
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(task.due_date, date(2027, 1, 20))

    def test_invalid_create_does_not_save_and_shows_errors(self):
        for overrides, field in [
            ({"title": "  "}, "title"),
            ({"title": "x" * 201}, "title"),
            ({"status": "invalid"}, "status"),
            ({"due_date": "not-a-date"}, "due_date"),
        ]:
            with self.subTest(field=field):
                response = self.client.post(
                    reverse("tasks:create"), self.task_data(**overrides)
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.assertEqual(Task.objects.count(), 2)

    def test_create_accepts_optional_fields_empty(self):
        response = self.client.post(
            reverse("tasks:create"), self.task_data(description="", due_date="")
        )
        task = Task.objects.get(title="A new task")
        self.assertRedirects(response, task.get_absolute_url())
        self.assertIsNone(task.due_date)
        self.assertEqual(task.description, "")
        self.assertContains(self.client.get(task.get_absolute_url()), "No description.")

    def test_detail_renders_fields_and_escapes_user_content(self):
        self.task.description = "<script>alert('unsafe')</script>\nSecond line"
        self.task.save()
        response = self.client.get(self.task.get_absolute_url())
        self.assertContains(response, escape(self.task.title))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>")
        self.assertContains(response, "Second line")

    def test_other_users_task_is_not_accessible_by_id(self):
        for name in ["detail", "update", "delete"]:
            url = reverse(f"tasks:{name}", args=[self.other_task.pk])
            for method in [self.client.get, self.client.post]:
                with self.subTest(name=name, method=method.__name__):
                    self.assertEqual(
                        method(url, self.task_data()).status_code,
                        405 if name == "detail" and method == self.client.post else 404,
                    )
        self.other_task.refresh_from_db()
        self.assertEqual(self.other_task.title, "Private task")
        self.assertEqual(self.other_task.owner, self.other)

    def test_missing_task_returns_not_found(self):
        for name in ["detail", "update", "delete"]:
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(reverse(f"tasks:{name}", args=[99999])).status_code,
                    404,
                )

    def test_update_changes_fields_but_not_owner(self):
        url = reverse("tasks:update", args=[self.task.pk])
        self.task.due_date = date(2027, 1, 20)
        self.task.save()
        self.assertContains(self.client.get(url), 'value="2027-01-20"')
        response = self.client.post(
            url,
            self.task_data(
                title="Updated task",
                owner=self.other.pk,
                status=Task.Status.DONE,
                due_date="",
            ),
        )
        self.assertRedirects(response, self.task.get_absolute_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Updated task")
        self.assertEqual(self.task.owner, self.owner)
        self.assertEqual(self.task.status, Task.Status.DONE)
        self.assertIsNone(self.task.due_date)

    def test_invalid_update_preserves_existing_task(self):
        response = self.client.post(
            reverse("tasks:update", args=[self.task.pk]),
            self.task_data(title=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Owner's task")

    def test_delete_get_only_confirms_and_post_deletes(self):
        url = reverse("tasks:delete", args=[self.task.pk])
        response = self.client.get(url)
        self.assertContains(response, "Yes, delete task")
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())
        response = self.client.post(url, follow=True)
        self.assertRedirects(response, reverse("tasks:list"))
        self.assertContains(response, "Task deleted.")
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertTrue(Task.objects.filter(pk=self.other_task.pk).exists())

    def test_task_mutations_require_csrf_and_valid_token_allows_create(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        for url in [
            reverse("tasks:create"),
            reverse("tasks:update", args=[self.task.pk]),
            reverse("tasks:delete", args=[self.task.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(
                    client.post(url, self.task_data()).status_code, 403
                )
        self.assertEqual(Task.objects.count(), 2)
        client.get(reverse("tasks:create"))
        response = client.post(
            reverse("tasks:create"),
            self.task_data(csrfmiddlewaretoken=client.cookies["csrftoken"].value),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Task.objects.filter(title="A new task", owner=self.owner).exists())


class HealthTests(TestCase):
    def test_health_is_public_and_checks_database(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_database_failure_returns_service_unavailable_and_logs(self):
        with patch(
            "tasks.views.connection.cursor",
            side_effect=OperationalError("database unavailable"),
        ):
            with self.assertLogs("tasks.views", level="ERROR") as logs:
                response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertIn("Database health check failed.", logs.output[0])
