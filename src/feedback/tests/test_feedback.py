from __future__ import annotations

import pytest

from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory, PlanFactory, PledgeFactory
from feedback.models import UserFeedback
from feedback.tests.factories import UserFeedbackFactory
from pages.models import ActionListPage

pytestmark = pytest.mark.django_db

CREATE_FEEDBACK_MUTATION = """
    mutation($input: UserFeedbackMutationInput!) {
        createUserFeedback(input: $input) {
            feedback {
                id
            }
            errors {
                field
                messages
            }
        }
    }
"""


def _mutate(graphql_client_query_data, **input_data):
    data = graphql_client_query_data(
        CREATE_FEEDBACK_MUTATION,
        variables={'input': input_data},
    )
    result = data['createUserFeedback']
    assert result['errors'] == []
    return UserFeedback.objects.get(pk=result['feedback']['id'])


class TestFeedbackModel:
    def test_create_general_feedback(self):
        feedback = UserFeedbackFactory.create(type=UserFeedback.FeedbackType.GENERAL)
        assert feedback.type == ''

    def test_create_accessibility_feedback(self):
        feedback = UserFeedbackFactory.create(type=UserFeedback.FeedbackType.ACCESSIBILITY)
        assert feedback.type == 'accessibility'

    def test_create_action_feedback(self):
        plan = PlanFactory.create()
        action = ActionFactory.create(plan=plan)
        feedback = UserFeedbackFactory.create(
            plan=plan,
            type=UserFeedback.FeedbackType.ACTION,
            action=action,
        )
        assert feedback.type == 'action'
        assert feedback.action == action

    def test_create_category_feedback(self):
        plan = PlanFactory.create()
        ct = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=ct)
        feedback = UserFeedbackFactory.create(
            plan=plan,
            type=UserFeedback.FeedbackType.CATEGORY,
            category=category,
        )
        assert feedback.type == 'category'
        assert feedback.category == category

    def test_create_pledge_feedback(self):
        plan = PlanFactory.create()
        pledge = PledgeFactory.create(plan=plan)
        feedback = UserFeedbackFactory.create(
            plan=plan,
            type=UserFeedback.FeedbackType.PLEDGE,
            pledge=pledge,
        )
        assert feedback.type == 'pledge'
        assert feedback.pledge == pledge

    def test_fk_fields_are_optional(self):
        feedback = UserFeedbackFactory.create(
            type=UserFeedback.FeedbackType.GENERAL,
        )
        assert feedback.action is None
        assert feedback.category is None
        assert feedback.pledge is None

    def test_feedback_type_choices(self):
        values = [choice[0] for choice in UserFeedback.FeedbackType.choices]
        assert values == ['', 'accessibility', 'action', 'category', 'pledge']


class TestFeedbackGraphQL:
    def test_create_general_feedback(self, plan_with_pages, graphql_client_query_data):
        obj = _mutate(
            graphql_client_query_data,
            plan=plan_with_pages.identifier,
            type='',
            comment='General feedback',
            url='https://example.com/',
        )
        assert obj.type == ''

    def test_create_accessibility_feedback(self, plan_with_pages, graphql_client_query_data):
        obj = _mutate(
            graphql_client_query_data,
            plan=plan_with_pages.identifier,
            type='accessibility',
            comment='Accessibility issue',
            url='https://example.com/',
        )
        assert obj.type == 'accessibility'

    def test_create_action_feedback(self, plan_with_pages, graphql_client_query_data):
        action = ActionFactory.create(plan=plan_with_pages)
        obj = _mutate(
            graphql_client_query_data,
            plan=plan_with_pages.identifier,
            type='action',
            action=str(action.pk),
            comment='Action feedback',
            url='https://example.com/actions',
        )
        assert obj.type == 'action'
        assert obj.action == action

    def test_create_category_feedback(self, plan_with_pages, graphql_client_query_data):
        ct = CategoryTypeFactory.create(plan=plan_with_pages)
        category = CategoryFactory.create(type=ct)
        obj = _mutate(
            graphql_client_query_data,
            plan=plan_with_pages.identifier,
            type='category',
            category=str(category.pk),
            comment='Category feedback',
            url='https://example.com/categories',
        )
        assert obj.type == 'category'
        assert obj.category == category

    def test_create_pledge_feedback(self, plan_with_pages, graphql_client_query_data):
        pledge = PledgeFactory.create(plan=plan_with_pages)
        obj = _mutate(
            graphql_client_query_data,
            plan=plan_with_pages.identifier,
            type='pledge',
            pledge=str(pledge.pk),
            comment='Pledge feedback',
            url='https://example.com/pledges',
        )
        assert obj.type == 'pledge'
        assert obj.pledge == pledge

    @pytest.mark.parametrize('feedback_type', ['', 'accessibility', 'action', 'category', 'pledge'])
    def test_create_feedback_without_optional_fks(self, plan_with_pages, graphql_client_query_data, feedback_type):
        obj = _mutate(
            graphql_client_query_data,
            plan=plan_with_pages.identifier,
            type=feedback_type,
            comment='Feedback without FKs',
            url='https://example.com/',
        )
        assert obj.type == feedback_type
        assert obj.action is None
        assert obj.category is None
        assert obj.pledge is None

    def test_invalid_feedback_is_not_saved(self, plan_with_pages, graphql_client_query_data):
        data = graphql_client_query_data(
            CREATE_FEEDBACK_MUTATION,
            variables={
                'input': {
                    'plan': plan_with_pages.identifier,
                    'comment': 'Feedback',
                    'url': 'https://example.com/',
                    'email': 'not-an-email',
                },
            },
        )
        result = data['createUserFeedback']
        assert result['feedback'] is None
        assert [error['field'] for error in result['errors']] == ['email']
        assert not UserFeedback.objects.exists()

    def test_latest_revision_is_saved(self, plan_with_pages, graphql_client_query_data):
        page = ActionListPage.objects.descendant_of(plan_with_pages.root_page).get()
        page.save_revision()
        obj = _mutate(
            graphql_client_query_data,
            plan=plan_with_pages.identifier,
            comment='Feedback',
            url='https://example.com/',
            pageId=str(page.pk),
        )
        assert obj.latest_revision is not None
        assert obj.latest_revision == page.get_latest_revision()
