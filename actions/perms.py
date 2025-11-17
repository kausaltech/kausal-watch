from __future__ import annotations

import typing
from functools import lru_cache

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.query_utils import Q
from wagtail.models import PAGE_PERMISSION_TYPES, GroupPagePermission, Page

from loguru import logger
from treelib import Tree

from kausal_common.datasets import models as dataset_models

from content.models import SiteGeneralContent
from indicators.models import (
    ActionIndicator,
    Dataset,
    DatasetLicense,
    Dimension,
    DimensionCategory,
    Indicator,
    IndicatorContactPerson,
    IndicatorDimension,
    IndicatorGoal,
    IndicatorGraph,
    IndicatorLevel,
    IndicatorValue,
    Quantity,
    RelatedIndicator,
    Unit,
)
from notifications.models import AutomaticNotificationTemplate, BaseTemplate, ContentBlock
from orgs.models import Organization, OrganizationPlanAdmin
from people.models import Person
from reports.models import Report, ReportType

from .models import (
    Action,
    ActionContactPerson,
    ActionImpact,
    ActionResponsibleParty,
    ActionSchedule,
    ActionStatus,
    ActionStatusUpdate,
    ActionTask,
    AttributeChoice,
    AttributeRichText,
    AttributeType,
    AttributeTypeChoiceOption,
    Category,
    CategoryType,
    GeneralPlanAdmin,
    ImpactGroup,
    ImpactGroupAction,
    MonitoringQualityPoint,
    Plan,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models.base import Model
    from django.db.models.query import QuerySet
    from wagtail.models.media import Collection

    from users.models import User as UserModel

User: UserModel = typing.cast('UserModel', get_user_model())

ACTIONS_APP = 'actions'
ALL_PERMS = ('view', 'change', 'publish', 'delete', 'add')


logger = logger.bind(name='actions.perms')

def _get_perm_obj_q(model: type[Model], perms: Iterable[str]) -> Q:
    content_type = ContentType.objects.get_for_model(model)
    full_perms = ['%s_%s' % (x, model._meta.model_name) for x in perms]
    return Q(content_type=content_type, codename__in=full_perms)


@lru_cache
def get_wagtail_contact_person_q() -> Q:
    q = Q(
        content_type__app_label='wagtaildocs',
        codename__in=('add_document', 'change_document', 'delete_document'),
        )
    q |= Q(
        content_type__app_label='wagtailimages',
        codename__in=('add_image', 'change_image', 'delete_image'),
    )
    q |= Q(
        content_type__app_label='wagtailcore',
        codename__in=['add_collection', 'view_collection'],
    )
    q |= Q(
        content_type__app_label='wagtailadmin',
        codename__in=('access_admin',),
    )
    return q


@lru_cache
def get_wagtail_plan_admin_perms():
    return Permission.objects.filter(
        content_type__app_label='wagtailcore',
        codename__in=[
            'change_collection',
            'delete_collection',
        ],
    )


@lru_cache
def get_action_contact_person_perms():
    # Add general permissions
    perm_q = _get_perm_obj_q(Action, ('view', 'change', 'publish'))
    perm_q |= _get_perm_obj_q(ActionTask, ('view', 'change', 'delete', 'add'))
    perm_q |= _get_perm_obj_q(Person, ('view', 'change', 'add'))
    perm_q |= _get_perm_obj_q(Plan, ('view',))
    perm_q |= _get_perm_obj_q(ActionContactPerson, ALL_PERMS)
    perm_q |= _get_perm_obj_q(ActionStatusUpdate, ALL_PERMS)
    perm_q |= _get_perm_obj_q(ActionIndicator, ('view',))
    perm_q |= _get_perm_obj_q(Indicator, ('view',))
    perm_q |= _get_perm_obj_q(dataset_models.DataPoint, ALL_PERMS)
    perm_q |= _get_perm_obj_q(dataset_models.Dataset, ALL_PERMS)

    perm_q |= Q(content_type__app_label='wagtailadmin', codename='access_admin')

    perm_q |= get_wagtail_contact_person_q()

    for model in (ActionResponsibleParty,):
        perm_q |= _get_perm_obj_q(model, ALL_PERMS)
    perm_q |= _get_perm_obj_q(Organization, ('view',))

    return Permission.objects.filter(perm_q)


@lru_cache
def get_indicator_contact_person_perms():
    perm_q = _get_perm_obj_q(Action, ('view',))
    perm_q |= _get_perm_obj_q(Person, ('view', 'change', 'add'))
    perm_q |= _get_perm_obj_q(ActionIndicator, ('view',))
    perm_q |= _get_perm_obj_q(Indicator, ('view', 'change'))
    perm_q |= _get_perm_obj_q(IndicatorGoal, ('view', 'change'))
    perm_q |= _get_perm_obj_q(IndicatorValue, ('view', 'change', 'add'))
    perm_q |= _get_perm_obj_q(IndicatorContactPerson, ALL_PERMS)

    perm_q |= Q(content_type__app_label='wagtailadmin', codename='access_admin')
    perm_q |= get_wagtail_contact_person_q()

    return Permission.objects.filter(perm_q)


def _get_or_create_group(name: str, perms: Iterable[Permission] | None = None, force_perm_sync: bool = False) -> Group:
    group, created = Group.objects.get_or_create(name=name)

    if perms is None:
        return group
    if not created and not force_perm_sync:
        return group

    existing_perms = set(group.permissions.all())
    new_perms = set(perms)
    if existing_perms != new_perms:
        group.permissions.clear()
        group.permissions.add(*new_perms)

    return group

def get_or_create_action_contact_person_group(force_perm_sync: bool = False) -> Group:
    perms = get_action_contact_person_perms()
    group = _get_or_create_group('Action contact persons', perms, force_perm_sync=force_perm_sync)
    return group


def get_or_create_indicator_contact_person_group(force_perm_sync: bool = False) -> Group:
    perms = get_indicator_contact_person_perms()
    group = _get_or_create_group('Indicator contact persons', perms, force_perm_sync=force_perm_sync)
    return group


def _sync_group_collection_perms(root_collection: Collection, group: Group, perms: Iterable[Permission]) -> None:
    from wagtail.models.media import GroupCollectionPermission as GCP  # noqa: N817

    current_perms = {obj.permission for obj in GCP.objects.filter(collection=root_collection, group=group)}
    for perm in perms:
        if perm not in current_perms:
            GCP.objects.create(collection=root_collection, group=group, permission=perm)
    for perm in current_perms:
        if perm not in perms:
            GCP.objects.get(collection=root_collection, group=group, permission=perm).delete()


def _sync_group_page_perms(root_pages: Iterable[Page], group: Group) -> None:
    # Delete all page permissions connected to another root page. (Root pages can be either plan root pages or
    # documentation root pages, and their respective translations are also root pages.)
    qs = GroupPagePermission.objects.filter(group=group)
    for page in root_pages:
        qs = qs.exclude(page=page)
    qs.delete()

    current_perms = GroupPagePermission.objects.filter(group=group).select_related('permission')
    perm_set = {gpp.permission.codename for gpp in current_perms}
    new_perm_set = {x[0] for x in PAGE_PERMISSION_TYPES}
    page_set = {gpp.page for gpp in current_perms}
    new_page_set = set(root_pages)
    if perm_set != new_perm_set or page_set != new_page_set:
        current_perms.delete()
        for codename in new_perm_set:
            for page in new_page_set:
                permission = Permission.objects.get(content_type__app_label='wagtailcore', codename=codename)
                GroupPagePermission.objects.create(page=page, group=group, permission=permission)


def _user_log(user: UserModel, message: str) -> None:
    logger.bind(**{'user.uuid': user.uuid, 'user.email': user.email}).info(message)


def _sync_contact_person_groups(user: UserModel, model: type[Action | Indicator]) -> None:
    plans = user.get_adminable_plans()
    groups = user.groups.filter(contact_person_for_plan__isnull=False).exclude(contact_person_for_plan__in=plans)

    if len(groups):
        _user_log(user, f'Removing {len(groups)} contact person groups for {model.__name__}')
        user.groups.remove(*groups)
    contact_person_groups = (
        plans.exclude(contact_person_group__isnull=True).values_list('contact_person_group', flat=True).distinct()
    )
    groups_to_add = Group.objects.filter(id__in=contact_person_groups).exclude(user=user)
    if len(groups_to_add):
        _user_log(user, f'Adding {len(groups_to_add)} contact person groups for {model.__name__}')
        user.groups.add(*groups_to_add)


def add_contact_person_perms(user: UserModel, model: type[Action | Indicator]):
    if model == Action:
        group = get_or_create_action_contact_person_group()
    else:
        group = get_or_create_indicator_contact_person_group()
    user.groups.add(group)

    # Make sure user is able to access the admin UI
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=['is_staff'])
    _sync_contact_person_groups(user, model)


def remove_contact_person_perms(user: UserModel, model: type[Action | Indicator]):
    if model == Action:
        group = get_or_create_action_contact_person_group()
    else:
        group = get_or_create_indicator_contact_person_group()
    user.groups.remove(group)
    _sync_contact_person_groups(user, model)


PLAN_ADMIN_PERMS: tuple[tuple[type[Model], tuple[str, ...]], ...] = (
    (Plan, ('view', 'change', 'publish', 'add')),
    (Action, ALL_PERMS),
    (ActionStatus, ALL_PERMS),
    (ActionSchedule, ALL_PERMS),
    (ActionImpact, ALL_PERMS),
    (AttributeType, ALL_PERMS),
    (AttributeTypeChoiceOption, ALL_PERMS),
    (AttributeChoice, ALL_PERMS),
    (AttributeRichText, ALL_PERMS),
    (CategoryType, ALL_PERMS),
    (Category, ALL_PERMS),
    (ImpactGroup, ALL_PERMS),
    (ImpactGroupAction, ALL_PERMS),
    (MonitoringQualityPoint, ALL_PERMS),
    (IndicatorLevel, ALL_PERMS),
    (ActionIndicator, ALL_PERMS),
    (Indicator, ALL_PERMS),
    (IndicatorGraph, ALL_PERMS),
    (IndicatorGoal, ALL_PERMS),
    (IndicatorValue, ALL_PERMS),
    (IndicatorContactPerson, ALL_PERMS),
    (RelatedIndicator, ALL_PERMS),
    (Unit, ALL_PERMS),
    (Quantity, ALL_PERMS),
    (Dataset, ALL_PERMS),
    (DatasetLicense, ALL_PERMS),
    (Dimension, ALL_PERMS),
    (DimensionCategory, ALL_PERMS),
    (IndicatorDimension, ALL_PERMS),
    (Organization, ALL_PERMS),
    (Person, ALL_PERMS),  # also delete perm for plan admin
    (ReportType, ALL_PERMS),
    (Report, ALL_PERMS),
    (SiteGeneralContent, ('add', 'view', 'change')),
    (BaseTemplate, ('add', 'view', 'change')),
    (AutomaticNotificationTemplate, ALL_PERMS),
    (ContentBlock, ALL_PERMS),
    (User, ('view',)),  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]
)


@lru_cache
def get_plan_admin_perms():
    all_perms = get_action_contact_person_perms()
    all_perms |= get_indicator_contact_person_perms()

    perm_q = Q()
    for model, perms in PLAN_ADMIN_PERMS:
        perm_q |= _get_perm_obj_q(model, perms)

    all_perms |= Permission.objects.filter(perm_q)
    all_perms |= get_wagtail_plan_admin_perms()

    return all_perms.distinct()


def get_or_create_plan_admin_group(force_perm_sync: bool = False) -> Group:
    perms = get_plan_admin_perms()
    group = _get_or_create_group('Plan admins', perms, force_perm_sync=force_perm_sync)
    return group


def sync_plan_admin_group_permissions(plan: Plan, perms: QuerySet[Permission] | None = None) -> None:
    if perms is None:
        perms = get_wagtail_plan_admin_perms()
    group = plan.admin_group
    assert group is not None
    if plan.root_collection is not None:
        _sync_group_collection_perms(plan.root_collection, group, perms)
    root_pages = set()
    if plan.site and plan.site.root_page:
        root_pages |= set(plan.site.root_page.get_translations(inclusive=True))
    root_pages |= set(plan.documentation_root_pages.all())
    _sync_group_page_perms(root_pages, group)


def sync_contact_person_group_permissions(plan: Plan, perms: QuerySet[Permission] | None = None) -> None:
    if perms is None:
        perms = Permission.objects.filter(get_wagtail_contact_person_q())
    assert plan.contact_person_group is not None
    group = plan.contact_person_group
    assert plan.root_collection is not None
    _sync_group_collection_perms(plan.root_collection, group, perms)


def sync_group_permissions() -> None:
    get_or_create_action_contact_person_group(force_perm_sync=True)
    get_or_create_indicator_contact_person_group(force_perm_sync=True)
    get_or_create_plan_admin_group(force_perm_sync=True)

    wagtail_perms = get_wagtail_plan_admin_perms()
    for plan in Plan.objects.exclude(admin_group__isnull=True):
        sync_plan_admin_group_permissions(plan, wagtail_perms)

    wagtail_perms = Permission.objects.filter(get_wagtail_contact_person_q())
    for plan in Plan.objects.filter(contact_person_group__isnull=False, root_collection__isnull=False):
        sync_contact_person_group_permissions(plan, wagtail_perms)


def _sync_plan_admin_groups(user: UserModel) -> None:
    person = user.get_corresponding_person()
    if person is None:
        return

    admin_plans = person.general_admin_plans.all()
    groups_to_remove = user.groups.exclude(admin_for_plan__isnull=True).exclude(admin_for_plan__in=admin_plans).distinct()
    if len(groups_to_remove):
        _user_log(user, 'Removing %d plan admin groups' % len(groups_to_remove))
        user.groups.remove(*groups_to_remove)

    plan_admin_groups = admin_plans.exclude(admin_group__isnull=True).values_list('admin_group', flat=True).distinct()
    groups_to_add = Group.objects.filter(id__in=plan_admin_groups).exclude(id__in=user.groups.all())
    if len(groups_to_add):
        _user_log(user, 'Adding %d plan admin groups' % len(groups_to_add))
        user.groups.add(*groups_to_add)


def remove_plan_admin_perms(user: UserModel) -> None:
    group = get_or_create_plan_admin_group()
    user.groups.remove(group)


def add_plan_admin_perms(user: UserModel):
    group = get_or_create_plan_admin_group()
    user.groups.add(group)

    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=['is_staff'])

    _sync_plan_admin_groups(user)


@lru_cache
def get_people_with_login_rights():
    all_orgs = _make_organization_tree(
        Organization.objects.order_by('path').all(),
    )
    return calculate_people_with_login_rights(
        superusers=set(
            Person.objects.filter(user__is_superuser=True).values_list('pk', flat=True),
        ),
        general_plan_admins=set(
            GeneralPlanAdmin.objects.values_list('person_id', flat=True),
        ),
        action_contact_persons=set(
            ActionContactPerson.objects.values_list('person_id', flat=True),
        ),
        indicator_contact_persons=set(
            IndicatorContactPerson.objects.values_list('person_id', flat=True),
        ),
        responsible_orgs=set(
            ActionResponsibleParty.objects.values_list('organization_id', flat=True),
        ),
        primary_orgs=set(
            Action.objects.values_list('primary_org_id', flat=True),
        ),
        indicator_orgs=set(
            Indicator.objects.values_list('organization_id', flat=True),
        ),
        organization_plan_admins=set(
            OrganizationPlanAdmin.objects.values_list('organization_id', 'person_id'),
        ),
        all_orgs=all_orgs,
    )


def calculate_people_with_login_rights(
    *,
    superusers: set[int],
    general_plan_admins: set[int],
    action_contact_persons: set[int],
    indicator_contact_persons: set[int],
    responsible_orgs: set[int],
    primary_orgs: set[int],
    indicator_orgs: set[int],
    organization_plan_admins: set[tuple[int, int]],
    all_orgs: Tree,
) -> set[int]:
    """
    Return a set of Person pks specifying all the persons who have any edit rights in the system.

    Receive a snapshot with sets of pks for all model instances in the db which are needed for determining
    if a person has some edit rights anywhere in the system to determine this.

    """
    persons_with_permissions_pks = superusers | general_plan_admins | action_contact_persons | indicator_contact_persons
    used_org_ids = responsible_orgs | primary_orgs | indicator_orgs
    for org_id, person_id in organization_plan_admins:
        org_and_descendants = set(all_orgs.expand_tree(org_id))
        if org_and_descendants.intersection(used_org_ids):
            persons_with_permissions_pks.add(person_id)

    return persons_with_permissions_pks


def _make_organization_tree(all_orgs: QuerySet[Organization]) -> Tree:
    orgs_by_path = {org.path: org for org in all_orgs}
    tree = Tree()
    root_id = -1
    tree.create_node(
        tag='<root>',
        identifier=root_id,
        parent=None,
    )
    for o in all_orgs:
        if o.is_root():
            parent_id = root_id
        else:
            parent_path = o.get_parent_path()
            assert parent_path is not None
            parent_id = orgs_by_path[parent_path].pk
        tree.create_node(
            tag=o.name,
            identifier=o.pk,
            parent=parent_id,
        )
    return tree
