import json
import pytest
import wagtail_factories
from graphene_django.utils.testing import graphql_query
from pytest_factoryboy import LazyFixture, register

from actions.tests import factories as actions_factories
from aplans.tests import factories as aplans_factories
# from admin_site.tests import factories as admin_site_factories
from content.tests import factories as content_factories
from images.tests import factories as images_factories
from indicators.tests import factories as indicators_factories
from users.tests import factories as users_factories
from pages.tests import factories as pages_factories
from people.tests import factories as people_factories

register(actions_factories.ActionContactFactory, 'action_contact')
register(actions_factories.ActionFactory)
register(actions_factories.ActionImpactFactory)
register(actions_factories.ActionImplementationPhaseFactory)
register(actions_factories.ActionResponsiblePartyFactory)
register(actions_factories.ActionScheduleFactory)
register(actions_factories.ActionStatusFactory)
register(actions_factories.CategoryFactory)
register(actions_factories.CategoryListBlockFactory)
register(actions_factories.CategoryMetadataRichTextFactory)
register(actions_factories.CategoryTypeMetadataFactory)
register(actions_factories.CategoryTypeMetadataChoiceFactory)
register(actions_factories.ImpactGroupFactory)
register(actions_factories.PlanFactory)
register(actions_factories.PlanDomainFactory)
register(aplans_factories.OrganizationClassFactory)
register(aplans_factories.OrganizationFactory)
# We don't register a fixture for admin_site_factories.ClientFactory (or anything that has a SubFactory on Client)
# because `client` is already taken by dango.test.Client and the following problem appears when we register the
# fixture with a different name:
# https://github.com/pytest-dev/pytest-factoryboy/issues/91
# register(admin_site_factories.ClientFactory, 'admin_site_client')
# register(admin_site_factories.ClientPlanFactory)
register(images_factories.AplansImageFactory)
register(indicators_factories.CommonIndicatorFactory)
register(indicators_factories.IndicatorFactory)
register(indicators_factories.IndicatorBlockFactory)
register(indicators_factories.IndicatorShowcaseBlockFactory)
register(indicators_factories.QuantityFactory)
register(indicators_factories.UnitFactory)
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
register(pages_factories.StaticPageFactory, parent=LazyFixture(lambda plan: plan.root_page))
register(people_factories.PersonFactory)
register(users_factories.UserFactory)
register(users_factories.UserFactory, 'superuser', is_superuser=True)
register(users_factories.UserFactory, 'plan_admin_user', general_admin_plans=LazyFixture(lambda plan: [plan]))
register(wagtail_factories.blocks.ImageChooserBlockFactory)
register(wagtail_factories.factories.CollectionFactory)


@pytest.fixture
def graphql_client_query(client):
    def func(*args, **kwargs):
        return graphql_query(*args, **kwargs, client=client, graphql_url='/v1/graphql/')
    return func


@pytest.fixture
def graphql_client_query_data(graphql_client_query):
    """Make a GraphQL request, make sure the `error` field is not present and return the `data` field."""
    def func(*args, **kwargs):
        response = graphql_client_query(*args, **kwargs)
        content = json.loads(response.content)
        assert 'errors' not in content
        return content['data']
    return func
