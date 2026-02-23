from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

import pytest

from kausal_common.strawberry.mutations import OP_INFO_FRAGMENT
from kausal_common.testing.graphql import OperationMessage, assert_operation_errors

from actions.models import Action, AttributeType, Category, CategoryType, Plan
from actions.models.attributes import AttributeChoice, AttributeTypeChoiceOption
from actions.tests.factories import AttributeTypeFactory, CategoryFactory, CategoryTypeFactory, PlanFactory
from orgs.tests.factories import OrganizationFactory

if TYPE_CHECKING:
    from orgs.models import Organization
    from users.models import User

pytestmark = pytest.mark.django_db


# -- Mutation query strings --------------------------------------------------


CREATE_PLAN = """
    mutation($input: PlanInput!) {
        plan {
            createPlan(input: $input) {
                ... on Plan {
                    id
                    identifier
                    name
                    shortName
                    primaryLanguage
                    otherLanguages
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT

DELETE_PLAN = """
    mutation($id: ID!) {
        plan {
            deletePlan(id: $id) {
                ...OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT

CREATE_ACTION = """
    mutation($input: ActionInput!) {
        action {
            createAction(input: $input) {
                ... on Action {
                    id
                    identifier
                    name
                    description
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT

CREATE_ACTION_WITH_METADATA = """
    mutation($input: ActionInput!) {
        action {
            createAction(input: $input) {
                ... on Action {
                    id
                    identifier
                    name
                    categories {
                        id
                        identifier
                        type { identifier }
                    }
                    attributes {
                        ... on AttributeChoice {
                            type { identifier }
                            choice { identifier name }
                        }
                    }
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT

CREATE_CATEGORY_TYPE = """
    mutation($input: CategoryTypeInput!) {
        plan {
            createCategoryType(input: $input) {
                ... on CategoryType {
                    id
                    identifier
                    name
                    usableForActions
                    usableForIndicators
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT

CREATE_CATEGORY = """
    mutation($input: CategoryInput!) {
        plan {
            createCategory(input: $input) {
                ... on Category {
                    id
                    identifier
                    name
                    order
                    parent { id }
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT

CREATE_ATTRIBUTE_TYPE = """
    mutation($input: AttributeTypeInput!) {
        plan {
            createAttributeType(input: $input) {
                ... on AttributeType {
                    id
                    identifier
                    name
                    format
                    helpText
                    choiceOptions {
                        id
                        identifier
                        name
                    }
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT

ADD_RELATED_ORGANIZATION = """
    mutation($input: AddRelatedOrganizationInput!) {
        plan {
            addRelatedOrganization(input: $input) {
                ... on Plan {
                    id
                    identifier
                    name
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT


# -- Permission tests ---------------------------------------------------------

class TestMutationPermissions:
    def test_plan_mutations_require_authentication(self, graphql_client_query):
        response = graphql_client_query(DELETE_PLAN, variables={'id': '999'})
        assert 'errors' in response

    def test_plan_mutations_require_superuser(self, graphql_client_query, client, user: User):
        client.force_login(user)
        response = graphql_client_query(DELETE_PLAN, variables={'id': '999'})
        assert 'errors' in response

    def test_action_mutations_require_authentication(self, graphql_client_query):
        response = graphql_client_query(
            CREATE_ACTION,
            variables={'input': {'planId': '1', 'name': 'x', 'identifier': 'x'}},
        )
        assert 'errors' in response

    def test_action_mutations_require_superuser(self, graphql_client_query, client, user: User):
        client.force_login(user)
        response = graphql_client_query(
            CREATE_ACTION,
            variables={'input': {'planId': '1', 'name': 'x', 'identifier': 'x'}},
        )
        assert 'errors' in response


# -- create_plan ---------------------------------------------------------------

class TestCreatePlan:
    def test_create_plan(self, graphql_client_query_data, client, superuser: User):
        client.force_login(superuser)
        org = OrganizationFactory.create()
        data = graphql_client_query_data(
            CREATE_PLAN,
            variables={'input': {
                'identifier': 'test-new-plan',
                'name': 'Test New Plan',
                'organizationId': str(org.pk),
                'primaryLanguage': 'en',
            }},
        )
        result = data['plan']['createPlan']
        assert result['identifier'] == 'test-new-plan'
        assert result['name'] == 'Test New Plan'
        assert result['primaryLanguage'] == 'en'
        assert Plan.objects.filter(identifier='test-new-plan').exists()

    def test_create_plan_with_duplicate_identifier(
        self, graphql_client_query, client, plan: Plan, organization: Organization, superuser: User
    ):
        client.force_login(superuser)
        response = graphql_client_query(
            CREATE_PLAN,
            variables={'input': {
                'identifier': plan.identifier,
                'name': 'Plan With Duplicate Identifier',
                'primaryLanguage': 'en',
                'organizationId': str(organization.pk),
            }},
        )
        assert 'errors' not in response
        messages = response['data']['plan']['createPlan']['messages']
        assert len(messages) == 1
        assert messages[0] == {
            'kind': 'VALIDATION',
            'message': 'Plan with this Identifier already exists.',
            'field': 'identifier',
            'code': 'unique',
        }
        assert 'id' not in response['data']['plan']['createPlan']

    def test_create_plan_with_features(self, graphql_client_query_data, client, superuser: User):
        client.force_login(superuser)
        org = OrganizationFactory.create()
        data = graphql_client_query_data(
            CREATE_PLAN,
            variables={'input': {
                'identifier': 'plan-with-features',
                'name': 'Plan With Features',
                'organizationId': str(org.pk),
                'primaryLanguage': 'fi',
                'otherLanguages': ['en'],
                'shortName': 'PWF',
                'features': {
                    'hasActionIdentifiers': True,
                    'hasActionPrimaryOrgs': True,
                },
            }},
        )
        result = data['plan']['createPlan']
        assert result['identifier'] == 'plan-with-features'
        assert result['shortName'] == 'PWF'
        assert result['primaryLanguage'] == 'fi'
        assert result['otherLanguages'] == ['en']

        plan = Plan.objects.get(identifier='plan-with-features')
        assert plan.features.has_action_identifiers is True
        assert plan.features.has_action_primary_orgs is True


# -- delete_plan ---------------------------------------------------------------

class TestDeletePlan:
    @staticmethod
    def _create_deletable_plan(**kwargs) -> Plan:
        plan = PlanFactory.create(**kwargs)
        plan.create_default_site()
        plan.save()
        return plan

    def test_delete_recently_created_plan(self, graphql_client_query_data, client, superuser: User):
        client.force_login(superuser)
        plan = self._create_deletable_plan(identifier='ephemeral-plan')
        plan_pk = plan.pk

        data = graphql_client_query_data(DELETE_PLAN, variables={'id': str(plan_pk)})
        assert data['plan']['deletePlan'] is None
        assert not Plan.objects.filter(pk=plan_pk).exists()

    def test_delete_plan_by_identifier(self, graphql_client_query_data, client, superuser: User):
        client.force_login(superuser)
        plan = self._create_deletable_plan(identifier='delete-by-ident')

        data = graphql_client_query_data(DELETE_PLAN, variables={'id': 'delete-by-ident'})
        assert data['plan']['deletePlan'] is None
        assert not Plan.objects.filter(pk=plan.pk).exists()

    def test_delete_plan_too_old(self, graphql_client_query, client, superuser: User):
        client.force_login(superuser)
        plan = self._create_deletable_plan(identifier='old-plan')
        # Bypass auto_now_add to set created_at in the past
        Plan.objects.filter(pk=plan.pk).update(created_at=timezone.now() - timedelta(days=3))

        response = graphql_client_query(DELETE_PLAN, variables={'id': str(plan.pk)})
        assert 'errors' in response
        assert Plan.objects.filter(pk=plan.pk).exists()

    def test_delete_plan_not_found(self, graphql_client_query, client, superuser: User):
        client.force_login(superuser)
        response = graphql_client_query(DELETE_PLAN, variables={'id': '999999'})
        assert 'errors' in response


# -- create_action -------------------------------------------------------------

class TestCreateAction:
    def test_create_action(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        data = graphql_client_query_data(
            CREATE_ACTION,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'New Climate Action',
                'identifier': 'new-action-1',
                'description': 'A test action',
            }},
        )
        result = data['action']['createAction']
        assert result['name'] == 'New Climate Action'
        assert result['identifier'] == 'new-action-1'
        assert result['description'] == 'A test action'
        assert Action.objects.filter(plan=plan, identifier='new-action-1').exists()

    def test_create_action_generates_identifier_when_not_required(
        self, graphql_client_query_data, client, superuser: User,
    ):
        """When hasActionIdentifiers is False, omitting identifier auto-generates one."""
        client.force_login(superuser)
        plan = PlanFactory.create()
        plan.features.has_action_identifiers = False
        plan.features.save()

        data = graphql_client_query_data(
            CREATE_ACTION,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'Auto ID Action',
                'identifier': '',
            }},
        )
        result = data['action']['createAction']
        assert result['identifier']  # Should be auto-generated, non-empty

    def test_create_action_requires_identifier_when_plan_has_them(
        self, graphql_client_query, client, superuser: User,
    ):
        client.force_login(superuser)
        plan = PlanFactory.create()
        plan.features.has_action_identifiers = True
        plan.features.save()

        response = graphql_client_query(
            CREATE_ACTION,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'Missing ID Action',
                'identifier': '',
            }},
        )
        data = response['data']['action']['createAction']
        assert 'errors' not in response
        assert 'messages' in data
        assert len(data['messages']) == 1
        assert data['messages'][0]['kind'] == 'VALIDATION'
        assert data['messages'][0]['message'] == 'Action identifier required for this plan.'

    def test_create_action_on_locked_plan(self, graphql_client_query, client, superuser: User):
        client.force_login(superuser)
        plan = PlanFactory.create(actions_locked=True)

        response = graphql_client_query(
            CREATE_ACTION,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'Should Fail',
                'identifier': 'nope',
            }},
        )
        assert 'errors' in response

    def test_create_action_with_categories(
        self, graphql_client_query_data, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        ct = CategoryTypeFactory.create(plan=plan, editable_for_actions=True, select_widget=CategoryType.SelectWidget.MULTIPLE)
        cat1 = CategoryFactory.create(type=ct, identifier='theme-a', name='Theme A')
        cat2 = CategoryFactory.create(type=ct, identifier='theme-b', name='Theme B')

        data = graphql_client_query_data(
            CREATE_ACTION_WITH_METADATA,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'Action with categories',
                'identifier': 'cat-action',
                'categoryIds': [str(cat1.pk), str(cat2.pk)],
            }},
        )
        result = data['action']['createAction']
        assert result['identifier'] == 'cat-action'
        cat_identifiers = {c['identifier'] for c in result['categories']}
        assert cat_identifiers == {'theme-a', 'theme-b'}

        action = Action.objects.get(pk=result['id'])
        assert set(action.categories.values_list('pk', flat=True)) == {cat1.pk, cat2.pk}

    def test_create_action_with_attribute_values(
        self, graphql_client_query_data, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        )
        opt = AttributeTypeChoiceOption.objects.create(
            type=attr_type, identifier='high', name='High', order=0,
        )

        data = graphql_client_query_data(
            CREATE_ACTION_WITH_METADATA,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'Action with attributes',
                'identifier': 'attr-action',
                'attributeValues': [
                    {'attributeTypeId': str(attr_type.pk), 'choiceId': str(opt.pk)},
                ],
            }},
        )
        result = data['action']['createAction']
        assert result['identifier'] == 'attr-action'
        assert len(result['attributes']) == 1
        assert result['attributes'][0]['type']['identifier'] == attr_type.identifier
        assert result['attributes'][0]['choice']['identifier'] == 'high'

        action = Action.objects.get(pk=result['id'])
        choice_attr = AttributeChoice.objects.get(
            content_type=ContentType.objects.get_for_model(Action),
            object_id=action.pk,
        )
        assert choice_attr.choice == opt

    def test_create_action_with_categories_and_attributes(
        self, graphql_client_query_data, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        ct = CategoryTypeFactory.create(plan=plan, editable_for_actions=True)
        cat = CategoryFactory.create(type=ct, identifier='mobility', name='Mobility')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        )
        opt = AttributeTypeChoiceOption.objects.create(
            type=attr_type, identifier='phase-1', name='Phase 1', order=0,
        )

        data = graphql_client_query_data(
            CREATE_ACTION_WITH_METADATA,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'Full action',
                'identifier': 'full-action',
                'categoryIds': [str(cat.pk)],
                'attributeValues': [
                    {'attributeTypeId': str(attr_type.pk), 'choiceId': str(opt.pk)},
                ],
            }},
        )
        result = data['action']['createAction']
        assert len(result['categories']) == 1
        assert result['categories'][0]['identifier'] == 'mobility'
        assert len(result['attributes']) == 1
        assert result['attributes'][0]['choice']['identifier'] == 'phase-1'

    def test_create_action_with_invalid_category(
        self, graphql_client_query, client, superuser: User, plan: Plan,
    ):
        """Category from another plan should be rejected."""
        client.force_login(superuser)
        other_plan = PlanFactory.create()
        ct = CategoryTypeFactory.create(plan=other_plan, editable_for_actions=True)
        cat = CategoryFactory.create(type=ct)

        response = graphql_client_query(
            CREATE_ACTION_WITH_METADATA,
            variables={'input': {
                'planId': str(plan.pk),
                'name': 'Bad category action',
                'identifier': 'bad-cat',
                'categoryIds': [str(cat.pk)],
            }},
        )
        assert 'errors' in response


# -- create_category_type ------------------------------------------------------

class TestCreateCategoryType:
    def test_create_category_type(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        data = graphql_client_query_data(
            CREATE_CATEGORY_TYPE,
            variables={'input': {
                'planId': str(plan.pk),
                'identifier': 'theme',
                'name': 'Theme',
                'usableForActions': True,
                'usableForIndicators': False,
            }},
        )
        result = data['plan']['createCategoryType']
        assert result['identifier'] == 'theme'
        assert result['name'] == 'Theme'
        assert result['usableForActions'] is True
        assert result['usableForIndicators'] is False

        ct = CategoryType.objects.get(pk=result['id'])
        assert ct.plan == plan
        # editableForActions should default to match usableForActions
        assert ct.editable_for_actions is True
        assert ct.editable_for_indicators is False


# -- create_category -----------------------------------------------------------

class TestCreateCategory:
    def test_create_category(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        ct = CategoryTypeFactory.create(plan=plan, editable_for_actions=True)

        data = graphql_client_query_data(
            CREATE_CATEGORY,
            variables={'input': {
                'typeId': str(ct.pk),
                'identifier': 'transport',
                'name': 'Transport',
                'order': 0,
            }},
        )
        result = data['plan']['createCategory']
        assert result['identifier'] == 'transport'
        assert result['name'] == 'Transport'
        assert result['parent'] is None
        assert Category.objects.filter(type=ct, identifier='transport').exists()

    def test_create_category_with_parent(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        ct = CategoryTypeFactory.create(plan=plan, editable_for_actions=True)
        parent = Category.objects.create(type=ct, identifier='energy', name='Energy')

        data = graphql_client_query_data(
            CREATE_CATEGORY,
            variables={'input': {
                'typeId': str(ct.pk),
                'identifier': 'solar',
                'name': 'Solar Energy',
                'parentId': str(parent.pk),
                'order': 0,
            }},
        )
        result = data['plan']['createCategory']
        assert result['identifier'] == 'solar'
        assert result['parent']['id'] == str(parent.pk)

    def test_create_category_on_non_editable_type(
        self, graphql_client_query, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        ct = CategoryTypeFactory.create(
            plan=plan, editable_for_actions=False, editable_for_indicators=False,
        )

        response = graphql_client_query(
            CREATE_CATEGORY,
            variables={'input': {
                'typeId': str(ct.pk),
                'identifier': 'nope',
                'name': 'Nope',
            }},
        )
        data = response['data']['plan']['createCategory']
        assert 'errors' not in response
        assert 'messages' in data
        assert len(data['messages']) == 1
        assert data['messages'][0]['kind'] == 'VALIDATION'
        assert data['messages'][0]['message'] == 'Categories of this type are not editable.'


# -- create_attribute_type -----------------------------------------------------

class TestCreateAttributeType:
    def test_create_text_attribute_type(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        data = graphql_client_query_data(
            CREATE_ATTRIBUTE_TYPE,
            variables={'input': {
                'planId': str(plan.pk),
                'identifier': 'notes',
                'name': 'Notes',
                'format': 'TEXT',
                'helpText': 'Additional notes',
            }},
        )
        result = data['plan']['createAttributeType']
        assert result['identifier'] == 'notes'
        assert result['format'] == 'TEXT'
        assert result['helpText'] == 'Additional notes'
        assert result['choiceOptions'] == []

        at = AttributeType.objects.get(pk=result['id'])
        assert at.scope_id == plan.pk

    def test_create_ordered_choice_attribute_type(
        self, graphql_client_query_data, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        data = graphql_client_query_data(
            CREATE_ATTRIBUTE_TYPE,
            variables={'input': {
                'planId': str(plan.pk),
                'identifier': 'priority',
                'name': 'Priority',
                'format': 'ORDERED_CHOICE',
                'choiceOptions': [
                    {'identifier': 'low', 'name': 'Low', 'order': 0},
                    {'identifier': 'medium', 'name': 'Medium', 'order': 1},
                    {'identifier': 'high', 'name': 'High', 'order': 2},
                ],
            }},
        )
        result = data['plan']['createAttributeType']
        assert result['identifier'] == 'priority'
        assert result['format'] == 'ORDERED_CHOICE'
        assert len(result['choiceOptions']) == 3
        option_ids = [opt['identifier'] for opt in result['choiceOptions']]
        assert option_ids == ['low', 'medium', 'high']

    def test_create_choice_attribute_type_requires_options(
        self, graphql_client_query, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        response = graphql_client_query(
            CREATE_ATTRIBUTE_TYPE,
            variables={'input': {
                'planId': str(plan.pk),
                'identifier': 'status',
                'name': 'Status',
                'format': 'ORDERED_CHOICE',
                # Missing choiceOptions
            }},
        )
        data = response['data']['plan']['createAttributeType']
        assert_operation_errors(
            data,
            [
                OperationMessage(
                    kind='VALIDATION',
                    message=(
                        'Choice options are required for ordered choice, unordered choice, '
                        'and optional choice with optional text attributes.'
                    )
                )
            ],
        )

    def test_create_text_attribute_type_rejects_choice_options(
        self, graphql_client_query, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        response = graphql_client_query(
            CREATE_ATTRIBUTE_TYPE,
            variables={'input': {
                'planId': str(plan.pk),
                'identifier': 'notes',
                'name': 'Notes',
                'format': 'TEXT',
                'choiceOptions': [
                    {'identifier': 'a', 'name': 'A', 'order': 0},
                ],
            }},
        )
        data = response['data']['plan']['createAttributeType']
        assert_operation_errors(
            data,
            [
                OperationMessage(
                    kind='VALIDATION',
                    message=(
                        'Choice options are only allowed for ordered choice, unordered choice, '
                        'and optional choice with optional text attributes.'
                    )
                )
            ],
        )


# -- add_related_organization --------------------------------------------------

class TestAddRelatedOrganization:
    def test_add_related_organization(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        org = OrganizationFactory.create()

        data = graphql_client_query_data(
            ADD_RELATED_ORGANIZATION,
            variables={'input': {
                'planId': str(plan.pk),
                'organizationId': str(org.pk),
            }},
        )
        result = data['plan']['addRelatedOrganization']
        assert result['identifier'] == plan.identifier
        assert plan.related_organizations.filter(pk=org.pk).exists()

    def test_add_related_organization_by_identifier(
        self, graphql_client_query_data, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        org = OrganizationFactory.create()

        data = graphql_client_query_data(
            ADD_RELATED_ORGANIZATION,
            variables={'input': {
                'planId': plan.identifier,
                'organizationId': str(org.pk),
            }},
        )
        result = data['plan']['addRelatedOrganization']
        assert result['identifier'] == plan.identifier
        assert plan.related_organizations.filter(pk=org.pk).exists()
