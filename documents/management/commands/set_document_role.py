from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from documents.models import DocumentRole


class Command(BaseCommand):
    help = "Assign a document role to an existing active user."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("role", choices=DocumentRole.Role.values)

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(
                username=options["username"], is_active=True
            )
        except user_model.DoesNotExist as exc:
            raise CommandError("No active user has that username.") from exc
        DocumentRole.objects.update_or_create(
            user=user, defaults={"role": options["role"]}
        )
        self.stdout.write(self.style.SUCCESS("Document role assigned."))
