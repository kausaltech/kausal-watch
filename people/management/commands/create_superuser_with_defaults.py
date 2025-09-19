from __future__ import annotations

from typing import cast, override
from uuid import UUID

from django.contrib.auth.management.commands.createsuperuser import Command as SuperUserCommand
from django.core.management.base import CommandError
from django.db import transaction

from actions.models import Plan
from admin_site.models import Client, EmailDomains
from orgs.models import Organization
from people.models import Person
from users.models import User

HELP = """
Used to create a superuser with all the prerequisites for logging in.

This command extends the default django command with Watch-specific additions.

"""

class Command(SuperUserCommand):
    help = HELP

    @override
    def add_arguments(self, parser):
        super().add_arguments(parser)
        _ = parser.add_argument(
            "--auth-backend",
            help="Specifies the used auth backend for the client. If empty or left out, use password login.",
            required=False
        )
        _ = parser.add_argument(
            "--organization",
            help="Specifies the name used for the organization and client.",
            required=True
        )
        _ = parser.add_argument(
            "--uuid",
            help="Set the User UUID",
            required=False,
        )
        _ = parser.add_argument(
            "--first-name",
            help="Set the first name",
            required=False,
        )
        _ = parser.add_argument(
            "--last-name",
            help="Set the last name",
            required=False,
        )

    def ensure_organization(self, organization_name: str) -> Organization:
        organization: Organization | None
        try:
            organization = Organization.objects.get(name=organization_name)
        except Organization.DoesNotExist:
            organization = None
        else:
            organization = cast('Organization', organization)
            if not organization.is_root():
                raise CommandError('Organization already exists but is not root.')
        if organization is None:
            organization = Organization.add_root(
                name=organization_name
            )
        return organization

    def ensure_client(self, organization_name: str, auth_backend: str, email_domain: str) -> Client:
        client, created = Client.objects.get_or_create(
            name=organization_name,
            defaults={'auth_backend': auth_backend},
        )
        if auth_backend:
            if client.auth_backend != auth_backend:
                raise CommandError(f'Client {organization_name} exists but has auth_backend {client.auth_backend}.')
        elif client.auth_backend not in ('', None):
            raise CommandError(
                f'Client {organization_name} exists but has auth_backend {client.auth_backend} (password auth was requested).'
            )

        try:
            existing_email_domain = EmailDomains.objects.get(domain=email_domain)
        except EmailDomains.DoesNotExist:
            EmailDomains.objects.get_or_create(
                domain=email_domain,
                client=client,
            )
        else:
            if existing_email_domain.client != client:
                raise CommandError(f'EmailDomain {email_domain} exists but has client {existing_email_domain.client}.')
        return client

    def ensure_person(self, user: User, organization: Organization) -> Person:
        person, created = Person.objects.get_or_create(
            email=user.email,
            user=user,
            defaults={
                'first_name': user.first_name,
                'last_name': user.last_name,
                'organization': organization,
            }
        )
        if person.organization.name != organization.name:
            raise CommandError(f'Person already exists but has organization {person.organization.name}.')
        person.save()
        return person

    def ensure_plan(self, organization: Organization, client: Client, person: Person) -> Plan | None:
        if Plan.objects.exists():
            return None
        plan = Plan.objects.create(
            name='Default Plan',
            identifier='default-plan',
            organization=organization,
        )
        return plan

    def enrich_user(self, user: User, auth_backend: str, first_name: str, last_name: str, uuid: UUID | None) -> None:
        user.is_staff = True
        user.first_name = first_name
        user.last_name = last_name
        if auth_backend:
            # Auth backend is empty only when password used
            user.set_unusable_password()
        if uuid is not None:
            user.uuid = uuid
        user.save()

    def ensure_superuser_has_defaults(
        self,
        user: User,
        auth_backend: str,
        organization_name: str,
        first_name: str,
        last_name: str,
        uuid: UUID | None = None
    ):
        """Apply app-specific defaults to ensure superuser can actually login."""
        assert user.is_superuser
        email_domain = user.email.split('@')[1].lower()
        self.enrich_user(user, auth_backend, first_name, last_name, uuid)
        organization = self.ensure_organization(organization_name)
        client = self.ensure_client(organization_name, auth_backend, email_domain)
        person = self.ensure_person(user, organization)
        self.ensure_plan(organization, client, person)

    @transaction.atomic
    def handle(self, *args, **options):
        old_superusers = list(User.objects.filter(is_superuser=True).values_list('pk', flat=True))
        if options['interactive'] and options['auth_backend']:
            print(
                'Please note Django will always ask for a password in interactive mode '
                'but it will not be used because you have chosen not to use password authentication.'
            )
        super().handle(*args, **options)
        new_superuser = User.objects.filter(is_superuser=True).exclude(pk__in=old_superusers).get()

        uuid = None
        if options['uuid']:
            try:
                uuid = UUID(options['uuid'])
            except ValueError as e:
                raise CommandError from e

        self.ensure_superuser_has_defaults(
            new_superuser,
            auth_backend=options['auth_backend'] or '',
            organization_name=options['organization'],
            first_name=options['first_name'] or '',
            last_name=options['last_name'] or '',
            uuid=uuid,
        )
