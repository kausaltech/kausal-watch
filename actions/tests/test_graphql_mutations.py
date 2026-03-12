from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

import pytest

from kausal_common.strawberry.mutations import OP_INFO_FRAGMENT
from kausal_common.testing.graphql import OperationMessage, assert_operation_errors

from actions.models import Action, AttributeType, Category, CategoryType, Plan
from actions.models.attributes import (
    AttributeChoice,
    AttributeChoiceWithText,
    AttributeRichText,
    AttributeText,
    AttributeTypeChoiceOption,
)
from actions.tests.factories import ActionFactory, AttributeTypeFactory, CategoryFactory, CategoryTypeFactory, PlanFactory
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

UPDATE_ACTIONS = """
    mutation($planId: ID!, $actions: [ActionUpdateInput!]!) {
        action {
            updateActions(planId: $planId, actions: $actions) {
                ... on BulkUpdateActionsResult {
                    count
                    ids
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
                'planId': plan.identifier,
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
                    {'attributeTypeId': str(attr_type.pk), 'value': {'choice': {'choiceId': str(opt.pk)}}},
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
                    {'attributeTypeId': str(attr_type.pk), 'value': {'choice': {'choiceId': str(opt.pk)}}},
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
                'planId': plan.identifier,
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
                'planId': plan.identifier,
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


# -- update_actions ------------------------------------------------------------

class TestUpdateActions:
    @staticmethod
    def _create_action(plan: Plan, identifier: str, name: str) -> Action:
        return ActionFactory.create(plan=plan, identifier=identifier, name=name)

    def test_update_description(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        a1 = self._create_action(plan, 'upd-1', 'Action 1')
        a2 = self._create_action(plan, 'upd-2', 'Action 2')

        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [
                    {'id': str(a1.pk), 'description': '<p>New desc 1</p>'},
                    {'id': str(a2.pk), 'description': '<p>New desc 2</p>'},
                ]
            },
        )
        result = data['action']['updateActions']
        assert result['count'] == 2
        assert str(a1.pk) in result['ids']
        assert str(a2.pk) in result['ids']

        a1.refresh_from_db()
        a2.refresh_from_db()
        assert a1.description == '<p>New desc 1</p>'
        assert a2.description == '<p>New desc 2</p>'

    def test_update_lead_paragraph(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'upd-lp', 'Action LP')

        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [
                    {'id': str(action.pk), 'leadParagraph': 'A short summary'},
                ],
            },
        )
        result = data['action']['updateActions']
        assert result['count'] == 1

        action.refresh_from_db()
        assert action.lead_paragraph == 'A short summary'

    def test_lookup_by_identifier_in_id_field(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'upd-ident', 'Action Ident')

        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [
                    {'id': 'upd-ident', 'description': '<p>Updated by identifier</p>'},
                ],
            },
        )
        result = data['action']['updateActions']
        assert result['count'] == 1
        assert result['ids'] == [str(action.pk)]

        action.refresh_from_db()
        assert action.description == '<p>Updated by identifier</p>'

    def test_update_choice_attributes(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'upd-ca', 'Action CA')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        )
        opt_low = AttributeTypeChoiceOption.objects.create(type=attr_type, identifier='low', name='Low', order=0)
        opt_high = AttributeTypeChoiceOption.objects.create(type=attr_type, identifier='high', name='High', order=1)

        # Set initial value
        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [
                    {
                        'id': str(action.pk),
                        'attributeValues': [
                            {'attributeTypeId': str(attr_type.pk), 'value': {'choice': {'choiceId': str(opt_low.pk)}}},
                        ],
                    }
                ],
            },
        )
        assert data['action']['updateActions']['count'] == 1

        action_ct = ContentType.objects.get_for_model(Action)
        choice = AttributeChoice.objects.get(type=attr_type, content_type=action_ct, object_id=action.pk)
        assert choice.choice == opt_low

        # Update to different value — should replace, not duplicate
        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [{
                    'id': str(action.pk), 'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'choice': {'choiceId': str(opt_high.pk)}}},
                    ]},
                ],
            },
        )
        assert data['action']['updateActions']['count'] == 1

        choices = AttributeChoice.objects.filter(type=attr_type, content_type=action_ct, object_id=action.pk)
        assert choices.count() == 1
        assert choices.get().choice == opt_high

    def test_update_rich_text_attributes(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'upd-rt', 'Action RT')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.RICH_TEXT,
        )

        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [{
                    'id': str(action.pk),
                    'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'richText':'<p>Rich text content</p>'}},
                    ]
                }],
            },
        )
        assert data['action']['updateActions']['count'] == 1

        action_ct = ContentType.objects.get_for_model(Action)
        rt = AttributeRichText.objects.get(type=attr_type, content_type=action_ct, object_id=action.pk)
        assert rt.text == '<p>Rich text content</p>'

        # Update — should replace
        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [{
                    'id': str(action.pk), 'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'richText':'<p>Updated content</p>'}},
                    ]
                }],
            },
        )
        rts = AttributeRichText.objects.filter(type=attr_type, content_type=action_ct, object_id=action.pk)
        assert rts.count() == 1
        assert rts.get().text == '<p>Updated content</p>'

    def test_update_responsible_parties(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'upd-rp', 'Action RP')
        org1 = OrganizationFactory.create(name='Org Primary')
        org2 = OrganizationFactory.create(name='Org Collab')
        plan.related_organizations.add(org1)
        plan.related_organizations.add(org2)
        plan.save()

        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [{
                    'id': str(action.pk), 'responsibleParties': [
                        {'organizationId': str(org1.pk), 'role': 'PRIMARY'},
                        {'organizationId': str(org2.pk), 'role': 'COLLABORATOR'},
                    ]
                },
            ]},
        )
        assert data['action']['updateActions']['count'] == 1

        parties = action.responsible_parties.all().order_by('order')
        assert parties.count() == 2
        assert parties[0].organization == org1
        assert parties[0].role == 'primary'
        assert parties[1].organization == org2
        assert parties[1].role == 'collaborator'

    def test_update_links(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'upd-lk', 'Action LK')

        data = graphql_client_query_data(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [{
                    'id': str(action.pk),
                    'links': [
                        {'url': 'https://example.com/doc1', 'title': 'Document 1'},
                        {'url': 'https://example.com/doc2', 'title': 'Document 2'},
                    ],
                }],
            },
        )
        assert data['action']['updateActions']['count'] == 1

        from actions.models.action import ActionLink
        links = ActionLink.objects.filter(action=action).order_by('order')
        assert links.count() == 2
        assert links[0].url == 'https://example.com/doc1'
        assert links[0].title == 'Document 1'
        assert links[1].url == 'https://example.com/doc2'

    def test_update_nonexistent_action(self, graphql_client_query, client, superuser: User):
        client.force_login(superuser)
        response = graphql_client_query(
            UPDATE_ACTIONS,
            variables={
                'planId': '999999',
                'actions': [
                    {'id': '999999', 'description': 'nope'},
                ],
            },
        )
        assert 'errors' in response

    def test_update_requires_superuser(self, graphql_client_query, client, user: User, plan: Plan):
        client.force_login(user)
        action = self._create_action(plan, 'upd-perm', 'Action Perm')
        response = graphql_client_query(
            UPDATE_ACTIONS,
            variables={
                'planId': str(plan.pk),
                'actions': [
                    {'id': str(action.pk), 'description': 'should fail'},
                ],
            },
        )
        assert 'errors' in response


# -- update_action (singular) --------------------------------------------------

UPDATE_ACTION = """
    mutation($planId: ID!, $input: ActionUpdateInput!) {
        action {
            updateAction(planId: $planId, input: $input) {
                ... on Action {
                    id
                    identifier
                    name
                    description
                    leadParagraph
                    categories {
                        id
                        identifier
                        type { identifier }
                    }
                    attributes {
                        ... on AttributeChoice {
                            type { identifier }
                            choice { identifier name }
                            text
                        }
                        ... on AttributeRichText {
                            type { identifier }
                            richTextValue: value
                        }
                        ... on AttributeText {
                            type { identifier }
                            textValue: value
                        }
                    }
                    responsibleParties {
                        organization { id name }
                        role
                    }
                    links {
                        url
                        title
                    }
                }
                ... OpInfo
            }
        }
    }
""" + OP_INFO_FRAGMENT


class TestUpdateAction:
    @staticmethod
    def _create_action(plan: Plan, identifier: str, name: str, **kwargs) -> Action:
        return ActionFactory.create(plan=plan, identifier=identifier, name=name, **kwargs)

    def test_update_description(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-desc', 'Action Desc')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {'id': str(action.pk), 'description': '<p>Updated description</p>'},
            },
        )
        result = data['action']['updateAction']
        assert result['description'] == '<p>Updated description</p>'

        action.refresh_from_db()
        assert action.description == '<p>Updated description</p>'

    def test_update_name_identifier_and_primary_org(
        self, graphql_client_query_data, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-editable', 'Original Name')
        org = OrganizationFactory.create(name='Primary Org')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'name': 'Updated Name',
                    'identifier': 'ua-editable-updated',
                    'primaryOrgId': str(org.pk),
                },
            },
        )
        result = data['action']['updateAction']
        assert result['name'] == 'Updated Name'
        assert result['identifier'] == 'ua-editable-updated'

        action.refresh_from_db()
        assert action.name == 'Updated Name'
        assert action.identifier == 'ua-editable-updated'
        assert action.primary_org == org

    def test_update_lead_paragraph(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-lp', 'Action LP')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {'id': str(action.pk), 'leadParagraph': 'A summary'},
            },
        )
        result = data['action']['updateAction']
        assert result['leadParagraph'] == 'A summary'

        action.refresh_from_db()
        assert action.lead_paragraph == 'A summary'

    def test_lookup_by_identifier(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        """update_action should accept an action identifier in the id field."""
        client.force_login(superuser)
        _action = self._create_action(plan, 'ua-ident', 'Action By Ident')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {'id': 'ua-ident', 'description': '<p>Found by identifier</p>'},
            },
        )
        result = data['action']['updateAction']
        assert result['identifier'] == 'ua-ident'
        assert result['description'] == '<p>Found by identifier</p>'

    def test_lookup_plan_by_identifier(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        """PlanId should accept a plan identifier string."""
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-plan-ident', 'Action Plan Ident')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': plan.identifier,
                'input': {'id': str(action.pk), 'description': '<p>Plan by ident</p>'},
            },
        )
        result = data['action']['updateAction']
        assert result['description'] == '<p>Plan by ident</p>'

    def test_update_choice_attribute(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-choice', 'Action Choice')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        )
        opt_low = AttributeTypeChoiceOption.objects.create(type=attr_type, identifier='low', name='Low', order=0)
        opt_high = AttributeTypeChoiceOption.objects.create(type=attr_type, identifier='high', name='High', order=1)

        # Set initial value
        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'choice': {'choiceId': str(opt_low.pk)}}},
                    ],
                },
            },
        )
        result = data['action']['updateAction']
        choice_attrs = [a for a in result['attributes'] if a.get('choice')]
        assert len(choice_attrs) == 1
        assert choice_attrs[0]['choice']['identifier'] == 'low'

        # Update to different value — should replace, not duplicate
        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'choice': {'choiceId': str(opt_high.pk)}}},
                    ],
                },
            },
        )
        result = data['action']['updateAction']
        choice_attrs = [a for a in result['attributes'] if a.get('choice')]
        assert len(choice_attrs) == 1
        assert choice_attrs[0]['choice']['identifier'] == 'high'

        action_ct = ContentType.objects.get_for_model(Action)
        assert AttributeChoice.objects.filter(type=attr_type, content_type=action_ct, object_id=action.pk).count() == 1

    def test_update_rich_text_attribute(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-rt', 'Action RT')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.RICH_TEXT,
        )

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'richText': '<p>Some rich text</p>'}},
                    ],
                },
            },
        )
        result = data['action']['updateAction']
        rt_attrs = [a for a in result['attributes'] if 'richTextValue' in a]
        assert len(rt_attrs) == 1
        assert rt_attrs[0]['richTextValue'] == '<p>Some rich text</p>'

        # Update — should replace
        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'richText': '<p>Updated rich text</p>'}},
                    ],
                },
            },
        )
        result = data['action']['updateAction']
        rt_attrs = [a for a in result['attributes'] if 'richTextValue' in a]
        assert len(rt_attrs) == 1
        assert rt_attrs[0]['richTextValue'] == '<p>Updated rich text</p>'

        action_ct = ContentType.objects.get_for_model(Action)
        assert AttributeRichText.objects.filter(type=attr_type, content_type=action_ct, object_id=action.pk).count() == 1

    def test_update_text_attribute(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-txt', 'Action Text')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.TEXT,
        )

        _data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'text': 'Plain text value'}},
                    ],
                },
            },
        )
        action_ct = ContentType.objects.get_for_model(Action)
        txt = AttributeText.objects.get(type=attr_type, content_type=action_ct, object_id=action.pk)
        assert txt.text == 'Plain text value'

    def test_update_attribute_by_identifier(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-attr-ident', 'Action Attr Ident')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            identifier='plain-notes',
            format=AttributeType.AttributeFormat.TEXT,
        )

        _data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {'attributeTypeId': attr_type.identifier, 'value': {'text': 'Resolved by identifier'}},
                    ],
                },
            },
        )
        action_ct = ContentType.objects.get_for_model(Action)
        txt = AttributeText.objects.get(type=attr_type, content_type=action_ct, object_id=action.pk)
        assert txt.text == 'Resolved by identifier'

    def test_update_optional_choice_with_text_attribute(
        self, graphql_client_query_data, client, superuser: User, plan: Plan,
    ):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-cwt', 'Action CWT')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,
        )
        opt = AttributeTypeChoiceOption.objects.create(type=attr_type, identifier='option-a', name='Option A', order=0)

        # Set with choice + text
        _data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {
                            'attributeTypeId': str(attr_type.pk),
                            'value': {'choice': {'choiceId': str(opt.pk), 'text': 'Rationale text'}},
                        },
                    ],
                },
            },
        )
        action_ct = ContentType.objects.get_for_model(Action)
        cwt = AttributeChoiceWithText.objects.get(type=attr_type, content_type=action_ct, object_id=action.pk)
        assert cwt.choice == opt
        assert cwt.text == 'Rationale text'

        # Update with null choice (text only)
        _data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'attributeValues': [
                        {
                            'attributeTypeId': str(attr_type.pk),
                            'value': {'choice': {'choiceId': None, 'text': 'No choice, just text'}},
                        },
                    ],
                },
            },
        )
        cwt.refresh_from_db()
        assert cwt.choice is None
        assert cwt.text == 'No choice, just text'

    def test_update_categories(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-cat', 'Action Cat')
        ct = CategoryTypeFactory.create(plan=plan, editable_for_actions=True, select_widget=CategoryType.SelectWidget.MULTIPLE)
        cat1 = CategoryFactory.create(type=ct, identifier='cat-a', name='Cat A')
        cat2 = CategoryFactory.create(type=ct, identifier='cat-b', name='Cat B')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'categoryIds': [str(cat1.pk), str(cat2.pk)],
                },
            },
        )
        result = data['action']['updateAction']
        cat_identifiers = {c['identifier'] for c in result['categories']}
        assert cat_identifiers == {'cat-a', 'cat-b'}

        # Replace with just one category
        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'categoryIds': [str(cat1.pk)],
                },
            },
        )
        result = data['action']['updateAction']
        cat_identifiers = {c['identifier'] for c in result['categories']}
        assert cat_identifiers == {'cat-a'}

    def test_update_responsible_parties(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-rp', 'Action RP')
        org1 = OrganizationFactory.create(name='Org Primary')
        org2 = OrganizationFactory.create(name='Org Collab')
        plan.related_organizations.add(org1, org2)

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'responsibleParties': [
                        {'organizationId': str(org1.pk), 'role': 'PRIMARY'},
                        {'organizationId': str(org2.pk), 'role': 'COLLABORATOR'},
                    ],
                },
            },
        )
        result = data['action']['updateAction']
        assert len(result['responsibleParties']) == 2
        assert result['responsibleParties'][0]['organization']['name'] == 'Org Primary'
        assert result['responsibleParties'][0]['role'] == 'PRIMARY'
        assert result['responsibleParties'][1]['organization']['name'] == 'Org Collab'
        assert result['responsibleParties'][1]['role'] == 'COLLABORATOR'

    def test_update_links(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-lk', 'Action Links')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'links': [
                        {'url': 'https://example.com/a', 'title': 'Link A'},
                        {'url': 'https://example.com/b', 'title': 'Link B'},
                    ],
                },
            },
        )
        result = data['action']['updateAction']
        assert len(result['links']) == 2
        assert result['links'][0]['url'] == 'https://example.com/a'
        assert result['links'][1]['title'] == 'Link B'

        # Replace links
        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'links': [{'url': 'https://example.com/c', 'title': 'Link C'}],
                },
            },
        )
        result = data['action']['updateAction']
        assert len(result['links']) == 1
        assert result['links'][0]['url'] == 'https://example.com/c'

    def test_update_multiple_fields_at_once(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        """Updating description, attributes, categories, and links in a single call."""
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-multi', 'Action Multi')
        ct = CategoryTypeFactory.create(plan=plan, editable_for_actions=True)
        cat = CategoryFactory.create(type=ct, identifier='theme-x', name='Theme X')
        attr_type = AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        )
        opt = AttributeTypeChoiceOption.objects.create(type=attr_type, identifier='medium', name='Medium', order=0)

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'description': '<p>Full update</p>',
                    'leadParagraph': 'Summary',
                    'categoryIds': [str(cat.pk)],
                    'attributeValues': [
                        {'attributeTypeId': str(attr_type.pk), 'value': {'choice': {'choiceId': str(opt.pk)}}},
                    ],
                    'links': [{'url': 'https://example.com', 'title': 'Example'}],
                },
            },
        )
        result = data['action']['updateAction']
        assert result['description'] == '<p>Full update</p>'
        assert result['leadParagraph'] == 'Summary'
        assert len(result['categories']) == 1
        assert result['categories'][0]['identifier'] == 'theme-x'
        assert len(result['attributes']) == 1
        assert len(result['links']) == 1

    def test_update_nonexistent_action(self, graphql_client_query, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        response = graphql_client_query(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {'id': '999999', 'description': 'nope'},
            },
        )
        assert 'errors' in response

    def test_update_requires_superuser(self, graphql_client_query, client, user: User, plan: Plan):
        client.force_login(user)
        action = self._create_action(plan, 'ua-perm', 'Action Perm')
        response = graphql_client_query(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {'id': str(action.pk), 'description': 'should fail'},
            },
        )
        assert 'errors' in response

    def test_no_change_returns_action(self, graphql_client_query_data, client, superuser: User, plan: Plan):
        """Sending an update with no fields should still return the action."""
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-noop', 'Action Noop', description='original')

        data = graphql_client_query_data(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {'id': str(action.pk)},
            },
        )
        result = data['action']['updateAction']
        assert result['id'] == str(action.pk)
        assert result['description'] == 'original'

    def test_update_rejects_unsupported_plan_id_field(self, graphql_client_query, client, superuser: User, plan: Plan):
        client.force_login(superuser)
        action = self._create_action(plan, 'ua-bad-field', 'Action Bad Field')

        response = graphql_client_query(
            UPDATE_ACTION,
            variables={
                'planId': str(plan.pk),
                'input': {
                    'id': str(action.pk),
                    'planId': str(plan.pk),
                },
            },
        )

        assert 'errors' in response
