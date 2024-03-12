import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan_with_single_task_moderation(plan_factory, workflow_factory, workflow_task_factory, action_factory):
    plan = plan_factory()
    workflow = workflow_factory()
    workflow_task_factory(workflow=workflow)
    plan.features.moderation_workflow = workflow
    action_factory(plan=plan)
    return plan


@pytest.fixture
def plan_with_double_task_moderation(plan_factory, workflow_task_factory, workflow_factory, action_factory):
    plan = plan_factory()
    workflow = workflow_factory()
    workflow_task_factory(workflow=workflow)
    workflow_task_factory(workflow=workflow)
    plan.features.moderation_workflow = workflow
    action_factory(plan=plan)
    return plan


@pytest.fixture
def action_contact_person_user_maker(action_contact_factory):
    def make_action_contact_person_with_role(plan, role):
        action = plan.actions.get()
        acp = action_contact_factory(action=action, role=role)
        return acp.person.user
    return make_action_contact_person_with_role


@pytest.fixture
def moderator_user_without_publishing_rights(plan_with_double_task_moderation, action_contact_person_user_maker):
    return action_contact_person_user_maker(plan_with_double_task_moderation, 'moderator')


@pytest.fixture
def moderator_user_with_publishing_rights(plan_with_single_task_moderation, action_contact_person_user_maker):
    return action_contact_person_user_maker(plan_with_single_task_moderation, 'moderator')


@pytest.fixture
def editor_user_without_publishing_rights_double(plan_with_double_task_moderation, action_contact_person_user_maker):
    return action_contact_person_user_maker(plan_with_double_task_moderation, 'editor')


@pytest.fixture
def editor_user_without_publishing_rights_single(plan_with_single_task_moderation, action_contact_person_user_maker):
    return action_contact_person_user_maker(plan_with_single_task_moderation, 'editor')


def test_action_moderator_has_publishing_rights(moderator_user_with_publishing_rights, plan_with_single_task_moderation):
    assert moderator_user_with_publishing_rights.can_publish_action(
        plan_with_single_task_moderation.actions.first()
    )


def test_action_moderator_has_no_publishing_rights(moderator_user_without_publishing_rights, plan_with_double_task_moderation):
    assert not moderator_user_without_publishing_rights.can_publish_action(
        plan_with_double_task_moderation.actions.first()
    )


def test_action_editor_has_no_publishing_rights(
        editor_user_without_publishing_rights_single,
        editor_user_without_publishing_rights_double,
        plan_with_single_task_moderation,
        plan_with_double_task_moderation
):
    assert not editor_user_without_publishing_rights_single.can_publish_action(
        plan_with_single_task_moderation.actions.first()
    )
    assert not editor_user_without_publishing_rights_double.can_publish_action(
        plan_with_double_task_moderation.actions.first()
    )


def test_action_editor_has_no_approval_rights(
        editor_user_without_publishing_rights_single,
        editor_user_without_publishing_rights_double,
        plan_with_single_task_moderation,
        plan_with_double_task_moderation
):
    assert not editor_user_without_publishing_rights_single.can_approve_action(
        plan_with_single_task_moderation.actions.first()
    )
    assert not editor_user_without_publishing_rights_double.can_approve_action(
        plan_with_double_task_moderation.actions.first()
    )


def test_action_moderator_has_approval_rights(
        moderator_user_with_publishing_rights,
        moderator_user_without_publishing_rights,
        plan_with_single_task_moderation,
        plan_with_double_task_moderation
):
    assert moderator_user_with_publishing_rights.can_approve_action(
        plan_with_single_task_moderation.actions.first()
    )
    assert moderator_user_without_publishing_rights.can_approve_action(
        plan_with_double_task_moderation.actions.first()
    )
