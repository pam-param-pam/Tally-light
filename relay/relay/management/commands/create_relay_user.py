from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a dashboard user"

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("Name cannot be empty.")
        User = get_user_model()
        if User.objects.filter(username=name).exists():
            raise CommandError(f"User {name!r} already exists.")
        password = getpass("Password: ")
        confirmation = getpass("Password (again): ")
        if password != confirmation:
            raise CommandError("Passwords do not match.")
        candidate = User(username=name)
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        User.objects.create_user(username=name, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created dashboard user {name!r}."))
