"""Create a DRF auth token for a user by email.

Usage:
    python manage.py create_auth_token <email>

The token is printed to stdout. Use it in API requests as:
    Authorization: Token <token>
"""

from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Create (or retrieve) a DRF auth token for the given user email."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email of the user to generate a token for.")

    def handle(self, *args, **options):
        email = options["email"]
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email: {email}")

        token, created = Token.objects.get_or_create(user=user)
        verb = "Created" if created else "Retrieved existing"
        self.stdout.write(f"{verb} token for {email}:")
        self.stdout.write(token.key)
        self.stdout.write(
            "\nUse it in API requests as:\n"
            f'  Authorization: Token {token.key}'
        )
