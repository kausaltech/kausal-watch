"""Choosers only offer what the user may see in the admin."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from wagtail.admin.viewsets import viewsets  # type: ignore[attr-defined]
from wagtail.snippets.models import get_snippet_models
from wagtail.snippets.views.chooser import SnippetChooserViewSet

import pytest
from generic_chooser.views import ModelChooserViewSet

from kausal_common.admin_site.choosers import ChooserViewSet

from actions.models import ActionChangeLogMessage, CategoryChangeLogMessage, IndicatorChangeLogMessage, PublicUser
from actions.perms import (
    get_action_contact_person_perms,
    get_indicator_contact_person_perms,
    get_plan_admin_perms,
    get_wagtail_plan_admin_perms,
    sync_group_permissions,
)
from actions.tests.factories import (
    ActionFactory,
    AttributeTypeFactory,
    CategoryFactory,
    CategoryLevelFactory,
    CategoryTypeFactory,
    PlanFactory,
    PledgeFactory,
)
from admin_site.scoped_choosers import (
    ChosenFromObjectListViewSetMixin,
    ChosenFromOfferedObjectsMixin,
    PermissionScopedSnippetChooserViewSet,
)
from admin_site.tests.factories import BuiltInFieldCustomizationFactory, ClientPlanFactory
from content.models import SiteGeneralContent
from datasets.tests.factories import DatasetSchemaScopeFactory
from documents.tests.factories import AplansDocumentFactory
from feedback.tests.factories import UserFeedbackFactory
from images.tests.factories import AplansImageFactory
from indicators.tests.factories import IndicatorFactory, IndicatorValueFactory, PlanDimensionFactory
from notifications.models import NotificationSettings
from notifications.tests.factories import BaseTemplateFactory
from pages.models import PageChangeLogMessage
from people.tests.factories import PersonFactory
from reports.tests.factories import ReportFactory, ReportTypeFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model

    from actions.models import Plan

pytestmark = pytest.mark.django_db

MARKER = 'OTHERPLAN'


@dataclass(frozen=True)
class Chooser:
    name: str
    url: str
    chosen_url: str
    create: Callable[[Plan], Model]
    query: Callable[[Model], dict[str, str]] = lambda _obj: {}
    # What a plan admin gets for their own plan's object: 'listed' (listed and choosable), 'hidden' (neither, as
    # the object's admin listing refuses them), 'choosable' (choosable, but listed only in context) or None (unchecked)
    own: Literal['listed', 'hidden', 'choosable'] | None = 'listed'
    # Organizations are a directory shared by all plans; their permission policy lets everyone view them
    others_visible: bool = False


def snippet(app_model: str, create: Callable[[Plan], Model], **kwargs) -> Chooser:
    base = f'/admin/snippets/choose/{app_model}/'
    return Chooser(app_model, base, f'{base}chosen/{{pk}}/', create, **kwargs)


def generic(prefix: str, create: Callable[[Plan], Model], **kwargs) -> Chooser:
    base = f'/admin/{prefix}/'
    return Chooser(prefix, base, f'{base}{{pk}}/', create, **kwargs)


def wagtail(prefix: str, create: Callable[[Plan], Model], **kwargs) -> Chooser:
    base = f'/admin/{prefix}/'
    return Chooser(prefix, base, f'{base}chosen/{{pk}}/', create, **kwargs)


def _indicator(plan: Plan):
    return IndicatorFactory.create(name=f'{MARKER} indicator', organization=plan.organization, plans=[plan])


def _general_content(plan: Plan):
    content = SiteGeneralContent.objects.get(plan=plan)
    content.site_title = f'{MARKER} site'
    content.save()
    return content


CHOOSERS = [
    snippet('actions/plan', lambda plan: plan),
    snippet('actions/planfeatures', lambda plan: plan.features),
    snippet('actions/pledge', lambda plan: PledgeFactory.create(plan=plan, name=f'{MARKER} pledge'), own='hidden'),
    snippet(
        'actions/publicuser',
        lambda plan: PublicUser.objects.create(email='otherplan@example.com', client=plan.clients.get().client),
        own='hidden',
    ),
    snippet(
        'actions/actionchangelogmessage',
        lambda plan: ActionChangeLogMessage.objects.create(
            plan=plan, action=ActionFactory.create(plan=plan, name=f'{MARKER} action'), content=MARKER
        ),
    ),
    snippet(
        'actions/categorychangelogmessage',
        lambda plan: CategoryChangeLogMessage.objects.create(
            plan=plan, category=CategoryFactory.create(type__plan=plan, name=f'{MARKER} category'), content=MARKER
        ),
    ),
    snippet(
        'actions/indicatorchangelogmessage',
        lambda plan: IndicatorChangeLogMessage.objects.create(plan=plan, indicator=_indicator(plan), content=MARKER),
    ),
    snippet(
        'pages/pagechangelogmessage',
        lambda plan: PageChangeLogMessage.objects.create(plan=plan, page=plan.root_page, content=MARKER),
        own='choosable',
    ),
    snippet('admin_site/client', lambda plan: plan.clients.get().client, own='hidden'),
    snippet('admin_site/builtinfieldcustomization', lambda plan: BuiltInFieldCustomizationFactory.create(plan=plan)),
    snippet('content/sitegeneralcontent', _general_content),
    snippet('feedback/userfeedback', lambda plan: UserFeedbackFactory.create(plan=plan, comment=MARKER)),
    snippet('notifications/basetemplate', lambda plan: BaseTemplateFactory.create(plan=plan)),
    snippet(
        'notifications/notificationsettings',
        lambda plan: NotificationSettings.objects.get_or_create(plan=plan)[0],
        own='hidden',
    ),
    snippet('orgs/organization', lambda plan: plan.organization, others_visible=True),
    generic('action-chooser', lambda plan: ActionFactory.create(plan=plan, name=f'{MARKER} action')),
    generic(
        'attribute-type-chooser',
        lambda plan: AttributeTypeFactory.create(scope=CategoryTypeFactory.create(plan=plan), name=f'{MARKER} attribute type'),
    ),
    generic('category-chooser', lambda plan: CategoryFactory.create(type__plan=plan, name=f'{MARKER} category')),
    generic('category-level-chooser', lambda plan: CategoryLevelFactory.create(type__plan=plan, name=f'{MARKER} level')),
    generic('category-type-chooser', lambda plan: CategoryTypeFactory.create(plan=plan, name=f'{MARKER} category type')),
    generic(
        'dataset-schema-chooser',
        lambda plan: DatasetSchemaScopeFactory.create(scope=plan, schema__name=f'{MARKER} schema').schema,
        own='choosable',
    ),
    generic('plan-chooser', lambda plan: plan),
    generic('client-chooser', lambda plan: plan.clients.get().client, own='hidden'),
    generic(
        'dimension-chooser',
        lambda plan: PlanDimensionFactory.create(plan=plan, dimension__name=f'{MARKER} dimension').dimension,
        own='choosable',
    ),
    generic(
        'indicator-value-chooser',
        lambda plan: IndicatorValueFactory.create(indicator=_indicator(plan)),
        query=lambda obj: {'indicator_id': str(obj.indicator_id)},
        own='choosable',
    ),
    generic('report-type-chooser', lambda plan: ReportTypeFactory.create(plan=plan, name=f'{MARKER} report type')),
    generic(
        'report-chooser',
        lambda plan: ReportFactory.create(type__plan=plan, name=f'{MARKER} report', is_complete=True),
    ),
    wagtail('indicator-chooser', _indicator),
    wagtail('organization-chooser', lambda plan: plan.organization, others_visible=True),
    generic('person-chooser', lambda plan: PersonFactory.create(first_name=MARKER, organization=plan.organization)),
    generic('task-person-chooser', lambda plan: PersonFactory.create(first_name=MARKER, organization=plan.organization)),
    wagtail(
        'images/chooser',
        lambda plan: AplansImageFactory.create(collection=plan.root_collection, title=f'{MARKER} image'),
        own=None,
    ),
    wagtail(
        'documents/chooser',
        lambda plan: AplansDocumentFactory.create(collection=plan.root_collection, title=f'{MARKER} document'),
        own=None,
    ),
]


@pytest.fixture
def other_plan():
    plan = PlanFactory.create(name=f'{MARKER} plan', organization__name=f'{MARKER} organization')
    plan.create_default_site()
    plan.save()
    ClientPlanFactory.create(plan=plan, client__name=f'{MARKER} client')
    return plan


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    # On a fresh test database the groups were synced, and these lists cached, before all apps' permissions existed
    for get_perms in (
        get_action_contact_person_perms,
        get_indicator_contact_person_perms,
        get_plan_admin_perms,
        get_wagtail_plan_admin_perms,
    ):
        get_perms.cache_clear()
    sync_group_permissions()
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.mark.parametrize('chooser', [c for c in CHOOSERS if not c.others_visible], ids=lambda c: c.name)
def test_chooser_hides_other_plans(admin_client, other_plan, chooser: Chooser):
    obj = chooser.create(other_plan)
    marker = MARKER if MARKER in str(obj) else str(obj)

    listing = admin_client.get(chooser.url, chooser.query(obj))
    assert listing.status_code in (200, 404)
    assert marker not in html.unescape(listing.content.decode())

    chosen = admin_client.get(chooser.chosen_url.format(pk=obj.pk))
    assert chosen.status_code != 200


@pytest.fixture
def own_plan(plan_with_pages):
    plan_with_pages.name = f'{MARKER} plan'
    plan_with_pages.save()
    organization = plan_with_pages.organization
    organization.name = f'{MARKER} organization'
    organization.save()
    return plan_with_pages


@pytest.mark.parametrize('chooser', [c for c in CHOOSERS if c.own is not None], ids=lambda c: c.name)
def test_chooser_offers_what_the_admin_listing_shows(admin_client, own_plan, chooser: Chooser):
    obj = chooser.create(own_plan)
    marker = MARKER if MARKER in str(obj) else str(obj)

    listed = marker in html.unescape(admin_client.get(chooser.url, chooser.query(obj)).content.decode())
    chosen = admin_client.get(chooser.chosen_url.format(pk=obj.pk)).status_code == 200
    if chooser.own == 'listed':
        assert listed
        assert chosen
    elif chooser.own == 'choosable':
        assert chosen
    else:
        assert not listed
        assert not chosen


# Choosers that may offer every object: quantities are shared by all plans, and everyone may view organizations
UNSCOPED_CHOOSERS = {'QuantityChooserViewSet', 'OrganizationChooserViewSet'}


def test_every_snippet_chooser_is_scoped():
    choosers = {vs.model: vs for vs in viewsets.viewsets if isinstance(vs, SnippetChooserViewSet)}
    for model, chooser in choosers.items():
        assert isinstance(chooser, PermissionScopedSnippetChooserViewSet), model
    assert set(choosers) == {m for m in get_snippet_models() if hasattr(m.snippet_viewset, 'chooser_viewset')}


def test_every_custom_chooser_looks_up_chosen_objects_among_those_it_offers():
    for viewset in viewsets.viewsets:
        if type(viewset).__name__ in UNSCOPED_CHOOSERS:
            continue
        if isinstance(viewset, ModelChooserViewSet):
            assert issubclass(viewset.chooser_mixin_class, ChosenFromOfferedObjectsMixin), type(viewset)
        elif isinstance(viewset, ChooserViewSet):
            assert isinstance(viewset, ChosenFromObjectListViewSetMixin), type(viewset)
