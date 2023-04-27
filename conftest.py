from __future__ import annotations

from typing import Protocol, Type
import factory
import json
import pytest
import typing
import wagtail_factories
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.urls import reverse
from factory import LazyAttribute, Sequence, SubFactory
from graphene_django.utils.testing import graphql_query
from pytest_factoryboy import LazyFixture, register
from pytest_django.asserts import assertRedirects
from rest_framework.authtoken.models import Token

from actions.tests import factories as actions_factories
# from admin_site.tests import factories as admin_site_factories
from content.tests import factories as content_factories
from images.tests import factories as images_factories
from indicators.tests import factories as indicators_factories
from notifications.tests import factories as notifications_factories
from orgs.tests import factories as orgs_factories
from pages.tests import factories as pages_factories
from people.tests import factories as people_factories
from users.tests import factories as users_factories

if typing.TYPE_CHECKING:
    from django.db.models import Model
    from wagtail.contrib.modeladmin.options import ModelAdmin
    from users.models import User
    import django.test.client


register(actions_factories.ActionContactFactory, 'action_contact')
register(actions_factories.ActionFactory)
register(actions_factories.ActionImpactFactory)
register(actions_factories.ActionImplementationPhaseFactory)
register(actions_factories.ActionResponsiblePartyFactory)
register(actions_factories.ActionScheduleFactory)
register(actions_factories.ActionStatusFactory)
register(actions_factories.CategoryFactory)
register(actions_factories.CategoryListBlockFactory)
register(actions_factories.CategoryTypeFactory)
register(actions_factories.CommonCategoryTypeFactory)
register(actions_factories.AttributeRichTextFactory)
register(actions_factories.AttributeCategoryChoiceFactory)
register(actions_factories.AttributeTypeFactory)
register(
    actions_factories.AttributeTypeFactory,
    'action_attribute_type',
    name=Sequence(lambda i: f"Action attribute type {i}"),
    object_content_type=LazyAttribute(lambda _: ContentType.objects.get(app_label='actions', model='action')),
    scope=SubFactory(actions_factories.PlanFactory),
)
register(actions_factories.AttributeTypeChoiceOptionFactory)
register(actions_factories.ImpactGroupFactory)
register(actions_factories.PlanFactory)
register(actions_factories.PlanFeaturesFactory)
register(actions_factories.PlanDomainFactory)
# We don't register a fixture for admin_site_factories.ClientFactory (or anything that has a SubFactory on Client)
# because `client` is already taken by django.test.Client and the following problem appears when we register the
# fixture with a different name:
# https://github.com/pytest-dev/pytest-factoryboy/issues/91
# register(admin_site_factories.ClientFactory, 'admin_site_client')
# register(admin_site_factories.ClientPlanFactory)
register(content_factories.SiteGeneralContentFactory)
register(images_factories.AplansImageFactory)
register(indicators_factories.CommonIndicatorFactory)
register(indicators_factories.IndicatorFactory)
register(indicators_factories.IndicatorBlockFactory)
register(indicators_factories.IndicatorShowcaseBlockFactory)
register(indicators_factories.QuantityFactory)
register(indicators_factories.UnitFactory)
register(notifications_factories.NotificationSettingsFactory)
register(orgs_factories.OrganizationClassFactory)
register(orgs_factories.OrganizationFactory)
register(orgs_factories.OrganizationIdentifierFactory)
register(orgs_factories.OrganizationPlanAdminFactory)
register(pages_factories.CardBlockFactory)
# NOTE: Due to a presumed bug in wagtail-factories, we deliberately do not register factories containing a
# ListBlockFactory. For these factories, we *should not use a fixture* but instead use the factory explicitly.
# https://github.com/wagtail/wagtail-factories/issues/40
# register(pages_factories.CardListBlockFactory)
register(pages_factories.CategoryPageFactory)
register(pages_factories.FrontPageHeroBlockFactory)
register(pages_factories.PageChooserBlockFactory, parent=LazyFixture(lambda plan: plan.root_page))
register(pages_factories.PageLinkBlockFactory)
# NOTE: Due to a presumed bug in wagtail-factories, we deliberately do not register factories containing a
# ListBlockFactory. For these factories, we *should not use a fixture* but instead use the factory explicitly.
# https://github.com/wagtail/wagtail-factories/issues/40
# register(pages_factories.QuestionAnswerBlockFactory)
register(pages_factories.QuestionBlockFactory)
register(pages_factories.RichTextBlockFactory)
register(pages_factories.StaticPageFactory, parent=LazyFixture(lambda plan_with_pages: plan_with_pages.root_page))
register(people_factories.PersonFactory, user=LazyFixture(lambda user: user))
register(people_factories.PersonFactory, 'plan_admin_person', user=LazyFixture(lambda user: user),
         general_admin_plans=LazyFixture(lambda plan: [plan]))
register(users_factories.UserFactory)
register(users_factories.UserFactory, 'superuser', is_superuser=True)
register(wagtail_factories.blocks.ImageChooserBlockFactory)
register(wagtail_factories.factories.CollectionFactory)


@pytest.fixture
@factory.django.mute_signals(post_save)
def plan_with_pages(plan):
    from actions.models.plan import set_default_page_creation

    with set_default_page_creation(True):
        plan.save()
    return plan


@pytest.fixture
def plan_admin_user(plan_admin_person):
    return plan_admin_person.user


@pytest.fixture
def action_contact_person(action):
    user = users_factories.UserFactory.create()
    person = people_factories.PersonFactory.create(contact_for_actions=[action], user=user)
    return person


@pytest.fixture
def action_contact_person_user(action_contact_person):
    return action_contact_person.user


@pytest.fixture
def graphql_client_query(client):
    def func(*args, **kwargs):
        response = graphql_query(*args, **kwargs, client=client, graphql_url='/v1/graphql/')
        return json.loads(response.content)
    return func


@pytest.fixture
def graphql_client_query_data(graphql_client_query):
    """Make a GraphQL request, make sure the `error` field is not present and return the `data` field."""
    def func(*args, **kwargs):
        response = graphql_client_query(*args, **kwargs)
        assert 'errors' not in response
        return response['data']
    return func


@pytest.fixture
def uuid(user):
    return str(user.uuid)


@pytest.fixture
def token(user):
    return Token.objects.create(user=user).key


@pytest.fixture
def contains_error():
    def func(response, code=None, message=None):
        if 'errors' not in response:
            return False
        expected_parts = {}
        if code is not None:
            expected_parts['extensions'] = {'code': code}
        if message is not None:
            expected_parts['message'] = message
        return any(expected_parts.items() <= error.items() for error in response['errors'])
    return func


@pytest.fixture(autouse=True)
def disable_search_autoupdate(settings):
    settings.WAGTAILSEARCH_BACKENDS['default']['AUTO_UPDATE'] = False


class ModelAdminEditTest(Protocol):
    def __call__(
        self, admin_class: Type[ModelAdmin], instance: Model, user: User,
        post_data: dict = {}, can_inspect: bool = True, can_edit: bool = True): ...


@pytest.fixture
def test_modeladmin_edit(client: django.test.client.Client) -> ModelAdminEditTest:
    def test_admin(
        admin_class: Type[ModelAdmin], instance: Model, user: User,
        post_data: dict = {}, can_inspect: bool = True, can_edit: bool = True
    ):
        adm = admin_class()
        edit_name = adm.url_helper.get_action_url_name('edit')
        edit_url = reverse(edit_name, kwargs=dict(instance_pk=instance.pk))
        client.logout()
        response = client.get(edit_url)
        # Should return a redirect to login page
        assert response.status_code == 302
        client.force_login(user)

        response = client.get(edit_url)
        if can_inspect:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

        # FIXME: Not working yet
        """
        # form = response.context_data['form']
        response = client.post(edit_url, data=dict(post_data))
        if can_edit:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

        if response.status_code != 302:
            form = response.context_data.get('form')
            if form is not None:
                print('Form errors:')
                print(form.errors)
                import ipdb; ipdb.set_trace()

        assertRedirects(response, adm.url_helper.get_action_url_name('index'))
        """

    return test_admin
