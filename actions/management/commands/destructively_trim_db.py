from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.core.management.base import BaseCommand
from django.db import ProgrammingError, connection, transaction
from django.db.models.signals import post_delete, post_save
from reversion.models import Revision as ReversionRevision, Version
from wagtail.models import DraftStateMixin, ModelLogEntry, PageLogEntry, Revision as WagtailRevision

import factory
from easy_thumbnails.models import Source, Thumbnail
from taggit.models import Tag

from actions.models.plan import Plan
from admin_site.models import Client
from images.models import AplansRendition
from orgs.models import Organization
from request_log.models import LoggedRequest
from users.models import User

if TYPE_CHECKING:
    from django.db.models import Model


class Command(BaseCommand):
    help = 'Delete plans and related data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--exclude-plan',
            metavar='IDENTIFIER',
            action='append',
            help='Exclude the plan with the specified identifier from deletion',
        )
        parser.add_argument(
            '--exclude-organization',
            metavar='UUID',
            action='append',
            help='Exclude the organization with the specified UUID from deletion',
        )
        parser.add_argument(
            '--exclude-client',
            metavar='ID',
            action='append',
            help='Exclude the client with the specified ID (primary key) from deletion',
        )
        parser.add_argument(
            '--no-confirm',
            action='store_true',
            help='Do not ask for confirmation but delete right away',
        )
        parser.add_argument('--thorough', action='store_true', help='Delete more data, including revision history and audit logs')

    def handle(self, *args, **options):
        if not settings.DEBUG or settings.DEPLOYMENT_TYPE == 'production':
            raise CommandError(
                'Sorry, for preventing accidents, this management command only works if DEBUG is true and '
                "DEPLOYMENT_TYPE is not 'production'.",
            )

        # Determine plans to delete
        all_identifiers = Plan.objects.values_list('identifier', flat=True)
        if not options.get('exclude_plan'):
            options['exclude_plan'] = []
        for identifier in options['exclude_plan']:
            if identifier not in all_identifiers:
                raise CommandError(f"No plan with identifier '{identifier}' exists.")
        plans_to_delete = Plan.objects.qs.exclude(identifier__in=options['exclude_plan'])
        plans_to_keep = Plan.objects.qs.exclude(id__in=plans_to_delete)
        delete_identifiers = plans_to_delete.values_list('identifier', flat=True)
        if options['exclude_plan']:
            self.stdout.write(f'The following plans will not be deleted: {", ".join(options["exclude_plan"])}')
        if delete_identifiers:
            self.stdout.write(f'The following plans will be deleted with all related data: {", ".join(delete_identifiers)}')

        # Determine organizations to delete
        orgs_to_keep = Organization.objects.qs.available_for_plans(plans_to_keep)
        if options['exclude_organization']:
            orgs_to_keep |= Organization.objects.filter(uuid__in=options['exclude_organization'])
        orgs_to_delete = Organization.objects.qs.exclude(id__in=orgs_to_keep)
        num_delete_suborgs = {}
        for org in orgs_to_delete.filter(depth=1):
            # Unnecessarily inefficient, but what the hell...
            num_delete_suborgs[org] = orgs_to_delete.filter(id__in=org.get_descendants()).count()
        if num_delete_suborgs:
            strings = []
            for org, n in num_delete_suborgs.items():
                string = org.name
                if n == 1:
                    string += ' (and 1 suborganization)'
                elif n > 1:
                    string += f' (and {n} suborganizations)'
                strings.append(string)
            self.stdout.write(f'The following organizations will be deleted: {", ".join(strings)}')

        self.stdout.write('Moreover, the following data will be deleted:')
        self.stdout.write("- all User instances that don't have a corresponding Person anymore")
        client_message = "- all Client instances that don't have a corresponding Plan anymore"
        if options['exclude_client']:
            client_names = Client.objects.filter(id__in=options['exclude_client']).values_list('name', flat=True)
            client_message += f' and are not among the following: {", ".join(client_names)}'
        self.stdout.write(client_message)
        self.stdout.write("- all Reversion Revision instances that don't have a corresponding User anymore")
        self.stdout.write("- all Wagtail Revision instances that don't have a corresponding User anymore")
        self.stdout.write("- all Wagtail ModelLogEntry instances that don't have a corresponding User anymore")
        self.stdout.write('- all logged requests')
        # if not options['keep_page_log']:
        #     self.stdout.write("- all entries of Wagtail's page log")
        # if not options['keep_model_log']:
        #     self.stdout.write("- all entries of Wagtail's model log")
        self.stdout.write('- all thumbnails')
        self.stdout.write('- all sessions')
        if not options['no_confirm']:
            confirmation = input('Do you want to proceed? [y/N] ').lower()
            if confirmation != 'y':
                self.stdout.write(self.style.WARNING('Aborted by user.'))
                return
        with factory.django.mute_signals(post_delete, post_save):
            self.delete_data(
                plans_to_delete,
                orgs_to_delete,
                clients_to_keep=options['exclude_client'],
                thorough=options['thorough'],
            )
        self.stdout.write("Rebuilding Wagtail's reference index...")
        call_command('rebuild_references_index')

    def delete_all(self, model: type[Model]) -> None:
        self.stdout.write(f'Deleting {model.__name__} instances...')
        _, by_type = model._default_manager.all().delete()
        self.print_deleted_instances_by_model(by_type)

    def _get_existing_object_ids_by_content_type(self, content_type_id: int, object_ids: list[str]) -> set[str]:
        model = ContentType.objects.get_for_id(content_type_id).model_class()
        if model is None:
            return set()
        return {str(pk) for pk in model._default_manager.filter(pk__in=object_ids).values_list('pk', flat=True)}

    def delete_userless_reversion_revisions(self) -> None:
        queryset = ReversionRevision.objects.filter(user__isnull=True)
        referenced_revision_ids: set[int] = set()
        for content_type_id in queryset.values_list('version__content_type_id', flat=True).distinct():
            if content_type_id is None:
                continue
            version_queryset = Version.objects.filter(revision__user__isnull=True, content_type_id=content_type_id)
            object_ids = list(version_queryset.values_list('object_id', flat=True).distinct())
            existing_object_ids = self._get_existing_object_ids_by_content_type(content_type_id, object_ids)
            if not existing_object_ids:
                continue
            referenced_revision_ids.update(
                version_queryset.filter(object_id__in=existing_object_ids).values_list('revision_id', flat=True)
            )

        _, by_type = queryset.exclude(id__in=referenced_revision_ids).delete()
        self.print_deleted_instances_by_model(by_type)

    def delete_userless_wagtail_revisions(self) -> None:
        queryset = WagtailRevision.objects.filter(user__isnull=True)
        revision_ids_to_keep: set[int] = set()
        for content_type_id in queryset.values_list('content_type_id', flat=True).distinct():
            content_type_queryset = queryset.filter(content_type_id=content_type_id)
            object_ids = list(content_type_queryset.values_list('object_id', flat=True).distinct())
            existing_object_ids = self._get_existing_object_ids_by_content_type(content_type_id, object_ids)
            if not existing_object_ids:
                continue
            revision_ids_to_keep.update(
                content_type_queryset.filter(object_id__in=existing_object_ids).values_list('id', flat=True)
            )

        _, by_type = queryset.exclude(id__in=revision_ids_to_keep).delete()
        self.print_deleted_instances_by_model(by_type)

    def delete_thoroughly(self):
        from django.contrib.admin.models import LogEntry

        from oauth2_provider.models import RefreshToken
        from social_django.models import Association, Code, Nonce, Partial

        from audit_logging.models import PlanScopedModelLogEntry, PlanScopedPageLogEntry
        from notifications.models import SentNotification

        try:
            from kausal_watch_extensions.models import AuthIDToken  # type: ignore[import-not-found]
        except ImportError:
            AuthIDToken = None  # type: ignore[misc,assignment]

        # Delete Reversion revisions without users
        self.delete_userless_reversion_revisions()
        # Delete Wagtail revisions without users
        self.delete_userless_wagtail_revisions()
        self.repair_has_unpublished_changes()
        # Delete Wagtail model log entries without users
        self.delete_all(ModelLogEntry)
        self.delete_all(PlanScopedModelLogEntry)
        self.delete_all(PlanScopedPageLogEntry)
        # Delete Wagtail page log entries
        self.delete_all(PageLogEntry)
        self.delete_all(LogEntry)

        self.delete_all(Association)
        self.delete_all(Nonce)
        self.delete_all(Code)
        self.delete_all(Partial)
        self.delete_all(SentNotification)
        self.delete_all(RefreshToken)
        self.delete_all(Tag)
        if AuthIDToken is not None:
            self.delete_all(AuthIDToken)

        with connection.cursor() as cursor, contextlib.suppress(ProgrammingError):
            cursor.execute('DELETE FROM postgres_search_indexentry;')

    @transaction.atomic
    def delete_data(
        self,
        plans_to_delete,
        orgs_to_delete,
        clients_to_keep: list[int] | None = None,
        thorough: bool = False,
    ):
        if clients_to_keep is None:
            clients_to_keep = []

        # Delete plans
        # Iterate over plans and call `delete()` individually because bulk deletion would not call `delete()` and leave
        # related objects in place.
        for plan in plans_to_delete:
            plan.delete()
            self.stdout.write(f'Deleted plan {plan.identifier}; information on deleted related rows not available.')
        # Delete organizations
        num_orgs = orgs_to_delete.count()
        orgs_to_delete.delete()
        # Treebeard won't tell us the deleted numbers -_-
        self.stdout.write(f'Deleted {num_orgs} organizations; information on deleted related rows not available.')
        # Delete users without persons
        _, by_type = User.objects.filter(person__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete clients without plans unless excluded
        _, by_type = Client.objects.filter(plans__isnull=True).exclude(id__in=clients_to_keep).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete Reversion revisions without users
        self.delete_userless_reversion_revisions()
        # Delete Wagtail revisions without users
        self.delete_userless_wagtail_revisions()
        self.repair_has_unpublished_changes()
        # Delete Wagtail model log entries without users
        _, by_type = ModelLogEntry.objects.filter(user__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete Wagtail page log entries without users
        _, by_type = PageLogEntry.objects.filter(user__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete all logged requests
        self.delete_all(LoggedRequest)
        # Delete thumbnails
        self.delete_all(Thumbnail)
        self.delete_all(Source)

        # Delete sessions
        self.delete_all(Session)

        # Delete all renditions
        self.delete_all(AplansRendition)

        if thorough:
            self.delete_thoroughly()

    def print_deleted_instances_by_model(self, by_type):
        for model_name, n in by_type.items():
            self.stdout.write(f'Deleted {n} instances of {model_name}.')

    def repair_has_unpublished_changes(self) -> None:
        # `latest_revision` is `on_delete=SET_NULL`, so deleting Revision rows leaves
        # DraftStateMixin instances with `latest_revision=NULL` while `has_unpublished_changes`
        # stays at whatever it was — possibly producing the impossible state
        # `has_unpublished_changes=True AND latest_revision IS NULL`. Fix the discrepancy here.
        for model in apps.get_models():
            if not issubclass(model, DraftStateMixin):
                continue
            updated_count = model._default_manager.filter(
                latest_revision__isnull=True,
                has_unpublished_changes=True,
            ).update(has_unpublished_changes=False)
            if updated_count:
                self.stdout.write(
                    f'Reset has_unpublished_changes on {updated_count} {model.__name__} instances with no latest_revision.'
                )
