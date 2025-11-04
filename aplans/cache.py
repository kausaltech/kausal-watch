from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, TypeVar, cast

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from wagtail.models import Page, Revision

import sentry_sdk

from kausal_common.datasets.models import Dataset, DatasetSchema, DatasetSchemaQuerySet

from aplans.graphql_types import WorkflowStateEnum

from actions.models import (
    Action,
    ActionImplementationPhase,
    ActionStatus,
    AttributeType,
    AttributeTypeChoiceOption,
    CategoryType,
    Plan,
)
from actions.models.category import Category
from pages.models import ActionListPage, IndicatorListPage
from reports.models import Report

if TYPE_CHECKING:
    from django.db.models.base import Model

    from kausal_common.datasets.models import DatasetScopeType

    from actions.models.action import ActionQuerySet
    from orgs.models import Organization, OrganizationQuerySet
    from pages.models import AplansPage
    from people.models import Person, PersonQuerySet
    from users.models import User

@dataclass
class PlanSpecificCache:
    plan: Plan
    organizations: dict[int, Organization] = field(default_factory=dict)
    persons: dict[int, Person] = field(default_factory=dict)
    organization_action_count_cache: OrganizationActionCountCache | None = None
    schemas_by_model: dict[type[Model], DatasetSchemaQuerySet] = field(default_factory=dict)

    @cached_property
    def category_types(self) -> list[CategoryType]:
        cts = list(self.plan.category_types.all())
        for ct in cts:
            ct.plan = self.plan
        return cts

    @cached_property
    def category_types_by_id(self) -> dict[int, CategoryType]:
        return {ct.id: ct for ct in self.category_types}

    @cached_property
    def action_statuses(self) -> list[ActionStatus]:
        return list(self.plan.action_statuses.all())

    @cached_property
    def plan_has_action_dependency_roles(self):
        return self.plan.action_dependency_roles.exists()

    @cached_property
    def implementation_phases(self) -> list[ActionImplementationPhase]:
        return list(self.plan.action_implementation_phases.all())

    @cached_property
    def translated_root_page(self) -> Page | None:
        root = self.plan.get_translated_root_page()
        if root is None:
            return None
        return root.specific

    @cached_property
    def action_list_page(self) -> ActionListPage | None:
        for page in self.visible_pages:
            if isinstance(page, ActionListPage):
                return page
        return None

    @cached_property
    def indicator_list_page(self) -> IndicatorListPage | None:
        for page in self.visible_pages:
            if isinstance(page, IndicatorListPage):
                return page
        return None

    @cached_property
    def visible_pages(self) -> list[AplansPage]:
        if self.translated_root_page is None:
            return []
        pages = self.translated_root_page.get_descendants(inclusive=True).live().public().specific()

        # We store the parent object in the page object itself to avoid extra DB hits.
        # MP_Node.get_parent() will use this cached parent object if it exists.
        # Also, we filter out pages that don't have a visible parent.
        pages_by_path = {page.path: page for page in pages}
        visible_pages = []
        for page in pages:
            parent_path = page._get_basepath(page.path, depth=page.depth - 1)
            parent = pages_by_path.get(parent_path)
            setattr(page, '_cached_parent_obj', parent)  # noqa: B010
            if page != self.translated_root_page and parent is None:
                continue
            visible_pages.append(page)

        return cast('list[AplansPage]', visible_pages)

    @cached_property
    def action_dataset_schemas(self) -> DatasetSchemaQuerySet:
        return DatasetSchema.objects.get_queryset().for_scope(self.plan)

    @cached_property
    def category_type_dataset_schemas_by_id(self) -> dict[int, list[DatasetSchema]]:
        qs = (
            DatasetSchema.objects.get_queryset()
            .for_model(CategoryType)
            .filter(scopes__scope_id__in=self.plan.category_types.values_list('id', flat=True))
        )
        by_id: dict[int, list[DatasetSchema]] = {}
        for ds in qs:
            by_id.setdefault(ds.pk, []).append(ds)
        return by_id

    def get_dataset_schemas_for_object(self, instance: DatasetScopeType) -> list[DatasetSchema]:
        if isinstance(instance, Action):
            assert instance.plan_id == self.plan.id
            return list(self.action_dataset_schemas)

        assert isinstance(instance, Category)
        schemas = self.category_type_dataset_schemas_by_id.get(instance.type_id, [])
        return schemas

    @cached_property
    def datasets_by_scope_by_schema(self) -> dict[str, dict[int, dict[str, Dataset]]]:
        result: dict[str, dict[int, dict[str, Dataset]]] = {}
        plan_content_type = ContentType.objects.get_for_model(Plan)
        category_type_content_type = ContentType.objects.get_for_model(CategoryType)
        action_datasets = Dataset.objects.filter(
            schema__scopes__scope_content_type=plan_content_type, schema__scopes__scope_id=self.plan.pk,
        )
        category_type_ids = self.plan.category_types.values_list('id', flat=True)
        category_datasets = Dataset.objects.filter(
            schema__scopes__scope_content_type=category_type_content_type, schema__scopes__scope_id__in=category_type_ids,
        )
        for ds in action_datasets:
            if ds.scope_id is not None and ds.schema is not None:
                result.setdefault('actions.Action', {}).setdefault(ds.scope_id, {})[str(ds.schema.uuid)] = ds
        for ds in category_datasets:
            if ds.scope_id is not None and ds.schema is not None:
                result.setdefault('actions.Category', {}).setdefault(ds.scope_id, {})[str(ds.schema.uuid)] = ds
        return result

    def populate_organizations(self, organizations: OrganizationQuerySet) -> None:
        """Add the organizations from a queryset to the cache, keeping any organizations that might already be in the cache."""
        for org in list(organizations):
            self.organizations[org.pk] = org

    def populate_persons(self, persons: PersonQuerySet) -> None:
        """Add the persons from a queryset to the cache, keeping any persons that might already be in the cache."""
        for person in list(persons):
            self.persons[person.pk] = person

    def get_organization(self, pk: int) -> Organization | None:
        return self.organizations.get(pk)

    def get_person(self, pk: int) -> Person | None:
        return self.persons.get(pk)

    def get_action_status(self, *, id: int | None = None, identifier: str | None = None) -> ActionStatus | None:
        # Must supply either id or identifier
        assert bool(id is None) != bool(identifier is None)

        for a_s in self.action_statuses:
            if id is not None:
                if a_s.id == id:
                    return a_s
            elif a_s.identifier == identifier:
                return a_s
        return None

    def get_action_implementation_phase(
        self, *, id: int | None = None, identifier: str | None = None
    ) -> ActionImplementationPhase | None:
        assert bool(id is None) != bool(identifier is None)
        for implementation_phase in self.implementation_phases:
            if id is not None:
                if implementation_phase.id == id:
                    return implementation_phase
            elif implementation_phase.identifier == identifier:
                return implementation_phase
        return None

    @cached_property
    def attribute_choice_options(self) -> dict[int, AttributeTypeChoiceOption]:
        result = {}
        plan_content_type = ContentType.objects.get_for_model(Plan)
        choice_formats = (
            AttributeType.AttributeFormat.ORDERED_CHOICE,
            AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,
            AttributeType.AttributeFormat.UNORDERED_CHOICE,
        )
        for attribute_type in (
            AttributeType.objects.filter(
                scope_content_type=plan_content_type,
            ).filter(
                scope_id=self.plan.pk,
            ).filter(
                format__in=choice_formats,
            )
        ).prefetch_related('choice_options'):
            for choice_option in attribute_type.choice_options.all():
                result[choice_option.pk] = choice_option
        return result

    def get_choice_option(self, pk) -> AttributeTypeChoiceOption:
        return self.attribute_choice_options[pk]

    @cached_property
    def latest_reports(self) -> list[Report]:
        qs = (
            Report.objects
                .filter(type__plan=self.plan)
                .order_by('type', '-start_date')
                .distinct('type')
        )
        return list(qs)

    @classmethod
    def fetch(cls, plan_id: int) -> Plan:
        plan = Plan.objects.filter(id=plan_id).select_related('features').first()
        assert plan is not None, "Invalid plan id"
        return plan

    def enrich_action(self, action: Action) -> None:
        if action.plan_id == self.plan.id:
            action.plan = self.plan
        if action.status_id is not None:
            action.status = self.get_action_status(id=action.status_id)
        if action.implementation_phase_id is not None:
            action.implementation_phase = self.get_action_implementation_phase(id=action.implementation_phase_id)


class WatchObjectCache:
    plan_caches: dict[int, PlanSpecificCache]
    plan_caches_by_identifier: dict[str, PlanSpecificCache]
    admin_plan_cache: PlanSpecificCache | None
    query_workflow_state: WorkflowStateEnum
    organization_action_count_cache: OrganizationActionCountCache | None
    user: User | None

    def __init__(self, user: User | None = None) -> None:
        self.plan_caches = {}
        self.plan_caches_by_identifier = {}
        self.admin_plan_cache = None
        self.query_workflow_state = WorkflowStateEnum.PUBLISHED
        self.user = user
        self.organization_action_count_cache = None

    def for_plan_id(self, plan_id: int) -> PlanSpecificCache:
        plan_cache = self.plan_caches.get(plan_id)
        if plan_cache is None:
            with sentry_sdk.start_span(op='cache.fetch', name='init plan cache'):
                plan = PlanSpecificCache.fetch(plan_id)
                plan_cache = PlanSpecificCache(plan)
            self.plan_caches[plan_id] = plan_cache
        return plan_cache

    def for_plan_identifier(self, plan_identifier: str) -> PlanSpecificCache:
        plan_cache = self.plan_caches_by_identifier.get(plan_identifier)
        if plan_cache is None:
            plan_id = Plan.objects.filter(identifier=plan_identifier).values_list('id', flat=True).first()
            assert plan_id is not None, "Invalid plan identifier"
            if plan_id in self.plan_caches:
                plan_cache = self.plan_caches[plan_id]
            else:
                plan_cache = self.for_plan_id(plan_id)
            self.plan_caches_by_identifier[plan_identifier] = plan_cache
        return plan_cache

    def for_plan(self, plan: Plan) -> PlanSpecificCache:
        return self.for_plan_id(plan.id)

    def for_page_path(self, path: str) -> PlanSpecificCache | None:
        for plan_cache in self.plan_caches.values():
            root_page = plan_cache.translated_root_page
            if root_page is None:
                continue
            if path.startswith(root_page.path):
                return plan_cache
        return None

class OrganizationActionCountCache:
    plans: list[Plan]
    data: dict[int, int]
    action_qs: ActionQuerySet
    organization_responsible_party_queryset_filter: Q

    def __init__(self, action_qs: ActionQuerySet) -> None:
        self.action_qs = action_qs
        self.organization_responsible_party_queryset_filter = Q()
        self.data = self._construct_cache_data()

    def _construct_cache_data(self) -> dict[int, int]:
        actions_without_revisions = self.action_qs.filter(
            latest_revision__isnull=True,
        ).prefetch_related(
            'responsible_parties__organization',
        )
        actions_with_revisions = self.action_qs.filter(latest_revision__isnull=False)
        organization_pks_from_revisions = set()
        revisions = Revision.objects.filter(pk__in=actions_with_revisions.values_list('latest_revision_id', flat=True))
        result: dict[int, int] = {}
        for revision in revisions:
            for arp in revision.content.get('responsible_parties', []):
                org_id = arp.get('organization')
                if org_id is None:
                    continue
                result[org_id] = result.get(org_id, 0) + 1
                organization_pks_from_revisions.add(org_id)
        for action in actions_without_revisions:
            for arp in action.responsible_parties.all():
                result[arp.organization_id] = result.get(arp.organization_id, 0) + 1
        self.organization_responsible_party_queryset_filter = Q(
            Q(responsible_actions__action__in=self.action_qs) |
            Q(id__in=organization_pks_from_revisions),
        )
        return result

    def get_action_count_for_organization(self, org_id: int) -> int:
        return self.data.get(org_id, 0)


T = TypeVar('T')
S = TypeVar('S')


class SerializedDictWithRelatedObjectCache(dict[T, S]):
    cache: PlanSpecificCache | None

    def __init__(self, *args, cache: PlanSpecificCache | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = cache
