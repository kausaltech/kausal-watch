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
from django.db.models import Exists, OuterRef
from django.db.models.functions import Cast
from django.db.models.signals import post_delete, post_save
from reversion.models import Revision as ReversionRevision
from wagtail.models import DraftStateMixin, ModelLogEntry, Page, PageLogEntry, Revision as WagtailRevision

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
    from uuid import UUID

    from django.db.models import Field, Model

    from orgs.models import OrganizationQuerySet


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
        parser.add_argument(
            '--prune-shared-reference-data',
            action='store_true',
            help=(
                'Also delete shared common-indicator framework data (common indicators, frameworks and their '
                'relations) that is not linked to any retained plan. Useful for producing a single-tenant export.'
            ),
        )

    def _validate_exclusions(self, options) -> None:
        # Validate every --exclude-* argument up front, so a typo can't silently fail open and
        # delete a plan, organization or client that was meant to be kept.
        if not options.get('exclude_plan'):
            options['exclude_plan'] = []
        all_identifiers = Plan.objects.values_list('identifier', flat=True)
        for identifier in options['exclude_plan']:
            if identifier not in all_identifiers:
                raise CommandError(f"No plan with identifier '{identifier}' exists.")

        exclude_organizations = options.get('exclude_organization') or []
        if exclude_organizations:
            all_org_uuids = {str(u) for u in Organization.objects.values_list('uuid', flat=True)}
            for uuid_str in exclude_organizations:
                if uuid_str not in all_org_uuids:
                    raise CommandError(f"No organization with UUID '{uuid_str}' exists.")

        exclude_clients = options.get('exclude_client') or []
        if exclude_clients:
            all_client_ids = {str(i) for i in Client.objects.values_list('id', flat=True)}
            for client_id in exclude_clients:
                if str(client_id) not in all_client_ids:
                    raise CommandError(f"No client with ID '{client_id}' exists.")

    def _organizations_to_keep(self, plans_to_keep, exclude_organization) -> OrganizationQuerySet:
        orgs_to_keep = Organization.objects.qs.available_for_plans(plans_to_keep)
        # available_for_plans() only returns plan organizations and their descendants. Also keep
        # their ancestors, or deleting the other organizations would remove a retained plan's
        # parent/root and corrupt the (treebeard) organization hierarchy.
        ancestor_ids: set[int] = set()
        for org in orgs_to_keep:
            ancestor_ids.update(org.get_ancestors().values_list('id', flat=True))
        if ancestor_ids:
            orgs_to_keep |= Organization.objects.filter(id__in=ancestor_ids)
        if exclude_organization:
            orgs_to_keep |= Organization.objects.filter(uuid__in=exclude_organization)
        return orgs_to_keep

    def _print_orgs_to_delete(self, orgs_to_delete: OrganizationQuerySet) -> None:
        num_delete_suborgs = {}
        for org in orgs_to_delete.filter(depth=1):
            # Unnecessarily inefficient, but what the hell...
            num_delete_suborgs[org] = orgs_to_delete.filter(id__in=org.get_descendants()).count()
        if not num_delete_suborgs:
            return
        strings = []
        for org, n in num_delete_suborgs.items():
            string = org.name
            if n == 1:
                string += ' (and 1 suborganization)'
            elif n > 1:
                string += f' (and {n} suborganizations)'
            strings.append(string)
        self.stdout.write(f'The following organizations will be deleted: {", ".join(strings)}')

    def _print_additional_deletions(self, options) -> None:
        self.stdout.write('Moreover, the following data will be deleted:')
        self.stdout.write("- all User instances that don't have a corresponding Person anymore")
        client_message = "- all Client instances that don't have a corresponding Plan anymore"
        if options['exclude_client']:
            client_names = Client.objects.filter(id__in=options['exclude_client']).values_list('name', flat=True)
            client_message += f' and are not among the following: {", ".join(client_names)}'
        self.stdout.write(client_message)
        if options['thorough']:
            self.stdout.write('- all Reversion Revision instances')
            self.stdout.write('- all Wagtail Revision instances')
            self.stdout.write('- all Wagtail ModelLogEntry instances')
            self.stdout.write('- all plan-scoped model/page log entries')
            self.stdout.write('- all Wagtail PageLogEntry instances')
        else:
            self.stdout.write('- all Wagtail Revision instances whose target object no longer exists')
            self.stdout.write('- all Wagtail ModelLogEntry instances whose target object no longer exists')
            self.stdout.write('- all Wagtail PageLogEntry instances whose target page no longer exists')
        self.stdout.write('- all logged requests')
        self.stdout.write('- all thumbnails')
        self.stdout.write('- all sessions')
        self.stdout.write('- all plan page trees (and their sites) left orphaned by deleted plans')
        self.stdout.write('- all wagtail_localize translation data whose translated object no longer exists')
        if options['prune_shared_reference_data']:
            self.stdout.write('- all common indicators (and their frameworks/relations) not linked to a retained plan')

    def handle(self, *args, **options):
        if not settings.DEBUG or settings.DEPLOYMENT_TYPE == 'production':
            raise CommandError(
                'Sorry, for preventing accidents, this management command only works if DEBUG is true and '
                "DEPLOYMENT_TYPE is not 'production'.",
            )

        # Determine plans to delete
        self._validate_exclusions(options)
        plans_to_delete = Plan.objects.qs.exclude(identifier__in=options['exclude_plan'])
        plans_to_keep = Plan.objects.qs.exclude(id__in=plans_to_delete)
        delete_identifiers = plans_to_delete.values_list('identifier', flat=True)
        if options['exclude_plan']:
            self.stdout.write(f'The following plans will not be deleted: {", ".join(options["exclude_plan"])}')
        if delete_identifiers:
            self.stdout.write(f'The following plans will be deleted with all related data: {", ".join(delete_identifiers)}')

        # Determine organizations to delete
        orgs_to_keep = self._organizations_to_keep(plans_to_keep, options.get('exclude_organization'))
        orgs_to_delete = Organization.objects.qs.exclude(id__in=orgs_to_keep)
        self._print_orgs_to_delete(orgs_to_delete)

        self._print_additional_deletions(options)
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
                prune_shared_reference_data=options['prune_shared_reference_data'],
            )
        self.stdout.write("Rebuilding Wagtail's reference index...")
        call_command('rebuild_references_index')

    def delete_all(self, model: type[Model]) -> None:
        self.stdout.write(f'Deleting {model.__name__} instances...')
        _, by_type = model._default_manager.all().delete()
        self.print_deleted_instances_by_model(by_type)

    def _get_object_id_cast_field(self, model: type[Model]) -> Field:
        pk_field: Field = model._meta.pk
        target_field = getattr(pk_field, 'target_field', None)
        while target_field is not None:
            pk_field = target_field
            target_field = getattr(pk_field, 'target_field', None)
        return pk_field.clone()

    def delete_entries_for_missing_objects(self, model: type[Model]) -> None:
        # Delete rows of a content_type/object_id-keyed model (Wagtail Revision and ModelLogEntry)
        # whose referenced object no longer exists. We key on object existence rather than on the
        # `user` FK: a revision or log entry for a deleted plan/page/object can still have a
        # surviving author, and it carries serialized object data, so retaining it would leak the
        # deleted customer's data. Conversely, entries for *kept* objects are always preserved here
        # (their object still exists), so a kept page never loses its live/latest revision.
        #
        # Per content type with a NOT EXISTS subquery, so we never materialise the live-object
        # ID set in Python memory or pass it as a giant IN predicate on production-sized dumps.
        content_type_ids = list(model._default_manager.values_list('content_type_id', flat=True).distinct())
        aggregated: dict[str, int] = {}

        for content_type_id in content_type_ids:
            target = ContentType.objects.get_for_id(content_type_id).model_class() if content_type_id is not None else None
            queryset = model._default_manager.filter(content_type_id=content_type_id)
            if target is None:
                # Stale content type (model removed from the codebase): the object cannot exist.
                _, by_type = queryset.delete()
            else:
                existing_object_subquery = target._default_manager.filter(
                    pk=Cast(OuterRef('object_id'), output_field=self._get_object_id_cast_field(target))
                )
                _, by_type = (
                    queryset.annotate(has_live_object=Exists(existing_object_subquery)).filter(has_live_object=False).delete()
                )
            for model_name, n in by_type.items():
                aggregated[model_name] = aggregated.get(model_name, 0) + n

        self.print_deleted_instances_by_model(aggregated)

    def delete_page_log_entries_for_missing_pages(self) -> None:
        # PageLogEntry references its object through a constraint-less `page` FK rather than
        # content_type/object_id, so it needs its own orphan check. Same rationale as
        # delete_entries_for_missing_objects: drop entries for pages that no longer exist
        # (regardless of author), keep entries for surviving pages.
        live_pages = Page.objects.filter(pk=OuterRef('page_id'))
        _, by_type = PageLogEntry.objects.annotate(has_live_page=Exists(live_pages)).filter(has_live_page=False).delete()
        self.print_deleted_instances_by_model(by_type)

    def delete_thoroughly(self):
        from django.contrib.admin.models import LogEntry

        from oauth2_provider.models import AccessToken, RefreshToken
        from social_django.models import Association, Code, Nonce, Partial

        from audit_logging.models import PlanScopedModelLogEntry, PlanScopedPageLogEntry
        from notifications.models import SentNotification

        try:
            from kausal_watch_extensions.models import AuthIDToken  # type: ignore[import-not-found]
        except ImportError:
            AuthIDToken = None  # type: ignore[misc,assignment]

        # Delete all revision history in thorough mode.
        self.delete_all(ReversionRevision)
        self.delete_all(WagtailRevision)
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
        self.delete_all(AccessToken)
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
        prune_shared_reference_data: bool = False,
    ):
        if clients_to_keep is None:
            clients_to_keep = []

        # Delete plans
        # Iterate over plans and call `delete()` individually because bulk deletion would not call `delete()` and leave
        # related objects in place.
        for plan in plans_to_delete:
            plan.delete()
            self.stdout.write(f'Deleted plan {plan.identifier}; information on deleted related rows not available.')
        # Delete plan page trees left orphaned by deleted plans (e.g. translated locale trees that
        # Plan.delete()'s bulk page deletion misses). Runs after plans are gone, so the retained set
        # is accurate, and before the orphan cleanups below, which then handle the cascaded pages.
        self.delete_orphaned_plan_pages()
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
        # Prune shared common-indicator framework data not linked to a retained plan. Runs after
        # plans and organizations (and therefore their indicators) are gone, so the "still in use"
        # check below sees only retained data. Must run before delete_orphaned_translation_data() so
        # any translation data left behind by the pruned rows is cleaned up in the same run.
        if prune_shared_reference_data:
            self.prune_unused_common_indicators()
        # Reversion cleanup is intentionally omitted here — thorough mode handles it with a full purge.
        # Delete Wagtail revisions for objects that no longer exist (regardless of author), then
        # repair the draft-state invariant on any kept page whose latest_revision was affected.
        self.delete_entries_for_missing_objects(WagtailRevision)
        self.repair_has_unpublished_changes()
        # Delete Wagtail model/page log entries for objects that no longer exist
        self.delete_entries_for_missing_objects(ModelLogEntry)
        self.delete_page_log_entries_for_missing_pages()
        # Delete wagtail_localize translation data for objects that no longer exist. Its own
        # post_delete cleanup was muted during deletion (see handle()), so it must be done here.
        self.delete_orphaned_translation_data()
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

    def delete_orphaned_plan_pages(self) -> None:
        """
        Delete Wagtail page trees of plans that no longer exist.

        Plan.delete() removes a plan's own-locale page tree, but a deleted plan can leave orphaned
        PlanRootPage subtrees behind — most notably its translated locale trees — together with
        their Sites. These carry the deleted plan's (translated) content, so retaining them would
        leak it into an export. Delete every plan root page, in any locale, that does not belong to
        a retained plan; the instance-level delete() cascades the descendant subtree and the root
        page's Site (unlike the bulk queryset delete in Plan.delete()).
        """
        from pages.models import PlanRootPage

        keep_root_ids: set[int] = set()
        for plan in Plan.objects.qs.all():
            if plan.site_id is None:
                continue
            keep_root_ids.update(plan.root_page.get_translations(inclusive=True).values_list('id', flat=True))
            keep_root_ids.update(plan.documentation_root_pages.values_list('id', flat=True))

        orphan_roots = PlanRootPage.objects.exclude(id__in=keep_root_ids)
        count = 0
        for root in orphan_roots:
            root.delete()
            count += 1
        if not count:
            self.stdout.write('No orphaned plan pages found.')
            return
        self.stdout.write(f'Deleted {count} orphaned plan root page(s), including their page subtrees and sites.')

    def delete_orphaned_translation_data(self) -> None:
        """
        Delete wagtail_localize translation data whose translated object no longer exists.

        wagtail_localize normally garbage-collects this data via a `post_delete` handler
        (`cleanup_translation_on_delete`), but the whole trim runs inside
        `factory.django.mute_signals(post_delete, post_save)`, so that handler never fires and the
        translation metadata for deleted pages/snippets is left behind. Since it carries the source
        text of the deleted objects, retaining it would leak other plans' content into any export.
        This mirrors that handler's cleanup, applied to every orphaned TranslatableObject at once.
        """
        try:
            from wagtail_localize.models import (
                OverridableSegment,
                RelatedObjectSegment,
                SegmentOverride,
                String,
                StringSegment,
                StringTranslation,
                Template,
                TemplateSegment,
                TranslatableObject,
            )
        except ImportError:
            return

        # A TranslatableObject is orphaned when no live instance shares its translation_key for the
        # object's content type. Collect the orphaned translation_keys per content type.
        orphan_keys: list[UUID] = []
        content_type_ids = list(TranslatableObject.objects.values_list('content_type_id', flat=True).distinct())
        for content_type_id in content_type_ids:
            model = ContentType.objects.get_for_id(content_type_id).model_class()
            keys = TranslatableObject.objects.filter(content_type_id=content_type_id).values_list(
                'translation_key',
                flat=True,
            )
            if model is None:
                # Stale content type (model removed from the codebase): the object cannot exist.
                orphan_keys.extend(keys)
                continue
            live_keys = set(model._default_manager.values_list('translation_key', flat=True))
            orphan_keys.extend(key for key in keys if key not in live_keys)

        aggregated: dict[str, int] = {}

        def accumulate(by_type: dict[str, int]) -> None:
            for model_name, n in by_type.items():
                aggregated[model_name] = aggregated.get(model_name, 0) + n

        if orphan_keys:
            # Segments must be deleted before their TranslatableObject because BaseSegment.context is
            # on_delete=PROTECT (same ordering as wagtail_localize's own cleanup_translation_on_delete).
            for model in (OverridableSegment, RelatedObjectSegment, StringSegment, TemplateSegment):
                _, by_type = model.objects.filter(context__object_id__in=orphan_keys).delete()
                accumulate(by_type)
            for model in (SegmentOverride, StringTranslation):
                _, by_type = model.objects.filter(context__object_id__in=orphan_keys).delete()
                accumulate(by_type)
            # Cascades to TranslationSource, Translation, TranslationLog and TranslationContext.
            _, by_type = TranslatableObject.objects.filter(translation_key__in=orphan_keys).delete()
            accumulate(by_type)

        # Source strings and templates are deduplicated globally, so deleting orphaned sources leaves
        # them behind once no surviving segment references them. Dropping a String cascades to its
        # StringTranslations, so this also removes orphaned translated text.
        _, by_type = String.objects.filter(segments__isnull=True).delete()
        accumulate(by_type)
        _, by_type = Template.objects.filter(segments__isnull=True).delete()
        accumulate(by_type)
        # Overrides/translations whose context was SET_NULL by an earlier deletion are orphans too.
        _, by_type = SegmentOverride.objects.filter(context__isnull=True).delete()
        accumulate(by_type)
        _, by_type = StringTranslation.objects.filter(context__isnull=True).delete()
        accumulate(by_type)

        if not aggregated:
            self.stdout.write('No orphaned translation data found.')
            return
        self.print_deleted_instances_by_model(aggregated)

    def prune_unused_common_indicators(self) -> None:
        """
        Delete shared common-indicator framework data not linked to any retained plan.

        Common indicators, their frameworks and relations are shared reference data that is not
        scoped to a plan, so a plan trim leaves the whole library behind. Keep only common
        indicators still linked to a retained plan (via PlanCommonIndicator) or referenced by a
        surviving Indicator (Indicator.common is on_delete=PROTECT, so those must be kept), delete
        the rest, then drop frameworks that end up with no common indicators.
        """
        from django.db.models import Q

        from indicators.models.common_indicator import CommonIndicator
        from indicators.models.metadata import Framework

        keep_ids = set(
            CommonIndicator.objects
            .filter(Q(plans__isnull=False) | Q(indicators__isnull=False))
            .values_list('id', flat=True)
            .distinct()
        )
        # Deleting a CommonIndicator cascades to FrameworkIndicator, PlanCommonIndicator,
        # RelatedCommonIndicator, CommonIndicatorNormalizator and CommonIndicatorDimension.
        _, by_type = CommonIndicator.objects.exclude(id__in=keep_ids).delete()
        self.print_deleted_instances_by_model(by_type)
        # Frameworks are only referenced through FrameworkIndicator (no plan FK), so any framework
        # left without common indicators is now unreferenced.
        _, by_type = Framework.objects.filter(common_indicators__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)

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
