from __future__ import annotations

from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command

import pytest

from aplans.wagtail_utils import _get_category_fields

from actions.attributes import AttributeType as AttributeTypeWrapper
from actions.models import Action, AttributeType
from actions.tests.factories import AttributeTypeFactory, CategoryTypeFactory, PlanFactory

pytestmark = pytest.mark.django_db


def create_action_attribute_type(plan, **kwargs):
    return AttributeTypeFactory.create(
        object_content_type=ContentType.objects.get_for_model(Action),
        scope=plan,
        **kwargs,
    )


def get_form_field_help_text(attribute_type, user, plan, obj):
    wrapper: AttributeTypeWrapper[Action] = AttributeTypeWrapper.from_model_instance(attribute_type)
    form_fields = wrapper.get_form_fields(user, plan, obj)
    return form_fields[0].django_field.help_text


class TestAttributeTypeAdminHelpText:
    def test_defaults_to_public_help_text(self, plan):
        at = create_action_attribute_type(plan, help_text='Public help', admin_help_text='')
        assert at.effective_admin_help_text == 'Public help'

    def test_overrides_public_help_text(self, plan):
        at = create_action_attribute_type(plan, help_text='Public help', admin_help_text='Admin help')
        assert at.effective_admin_help_text == 'Admin help'

    def test_public_help_text_is_unaffected(self, plan):
        at = create_action_attribute_type(plan, help_text='Public help', admin_help_text='Admin help')
        assert at.help_text_i18n == 'Public help'

    def test_form_field_uses_admin_help_text(self, plan, action, superuser):
        at = create_action_attribute_type(
            plan,
            format=AttributeType.AttributeFormat.TEXT,
            help_text='Public help',
            admin_help_text='Admin help',
        )
        assert get_form_field_help_text(at, superuser, plan, action) == 'Admin help'

    def test_form_field_falls_back_to_public_help_text(self, plan, action, superuser):
        at = create_action_attribute_type(
            plan,
            format=AttributeType.AttributeFormat.TEXT,
            help_text='Public help',
            admin_help_text='',
        )
        assert get_form_field_help_text(at, superuser, plan, action) == 'Public help'


class TestCategoryTypeAdminHelpText:
    def test_defaults_to_public_help_text(self, plan):
        ct = CategoryTypeFactory.create(plan=plan, help_text='Public help', admin_help_text='')
        assert ct.effective_admin_help_text == 'Public help'

    def test_overrides_public_help_text(self, plan):
        ct = CategoryTypeFactory.create(plan=plan, help_text='Public help', admin_help_text='Admin help')
        assert ct.effective_admin_help_text == 'Admin help'

    def test_action_form_field_uses_admin_help_text(self, plan, action):
        CategoryTypeFactory.create(
            plan=plan,
            identifier='cthelp',
            help_text='Public help',
            admin_help_text='Admin help',
            editable_for_actions=True,
        )
        fields = _get_category_fields(plan, Action, action)
        assert fields['categories_cthelp'].help_text == 'Admin help'

    def test_action_form_field_falls_back_to_public_help_text(self, plan, action):
        CategoryTypeFactory.create(
            plan=plan,
            identifier='cthelp',
            help_text='Public help',
            admin_help_text='',
            editable_for_actions=True,
        )
        fields = _get_category_fields(plan, Action, action)
        assert fields['categories_cthelp'].help_text == 'Public help'


class TestMoveHelpTextsToAdminCommand:
    def call(self, *args):
        out = StringIO()
        call_command('move_help_texts_to_admin', *args, stdout=out)
        return out.getvalue()

    def test_moves_attribute_type_help_text(self, plan):
        at = create_action_attribute_type(plan, help_text='Public help', admin_help_text='')
        self.call(plan.identifier)
        at.refresh_from_db()
        assert at.admin_help_text == 'Public help'
        assert at.help_text == ''

    def test_moves_category_type_help_text(self, plan):
        ct = CategoryTypeFactory.create(plan=plan, help_text='Public help', admin_help_text='')
        self.call(plan.identifier)
        ct.refresh_from_db()
        assert ct.admin_help_text == 'Public help'
        assert ct.help_text == ''

    def test_leaves_existing_admin_help_text_untouched(self, plan):
        at = create_action_attribute_type(plan, help_text='Public help', admin_help_text='Existing')
        self.call(plan.identifier)
        at.refresh_from_db()
        assert at.admin_help_text == 'Existing'
        assert at.help_text == 'Public help'

    def test_overwrites_with_force(self, plan):
        at = create_action_attribute_type(plan, help_text='Public help', admin_help_text='Existing')
        self.call(plan.identifier, '--force')
        at.refresh_from_db()
        assert at.admin_help_text == 'Public help'
        assert at.help_text == ''

    def test_leaves_other_plans_alone(self, plan):
        other_plan = PlanFactory.create()
        at = create_action_attribute_type(other_plan, help_text='Public help', admin_help_text='')
        self.call(plan.identifier)
        at.refresh_from_db()
        assert at.admin_help_text == ''
        assert at.help_text == 'Public help'

    def test_moves_translations(self, plan):
        at = create_action_attribute_type(
            plan,
            primary_language='en',
            other_languages=['fi'],
            help_text='Public help',
            admin_help_text='',
        )
        at.help_text_fi = 'Julkinen ohje'
        at.save()
        self.call(plan.identifier)
        at.refresh_from_db()
        assert at.admin_help_text == 'Public help'
        assert at.admin_help_text_fi == 'Julkinen ohje'
        assert at.help_text == ''
        assert not at.help_text_fi

    def test_dry_run_changes_nothing(self, plan):
        at = create_action_attribute_type(plan, help_text='Public help', admin_help_text='')
        self.call(plan.identifier, '--dry-run')
        at.refresh_from_db()
        assert at.admin_help_text == ''
        assert at.help_text == 'Public help'

    def test_unknown_plan_raises(self, plan):
        with pytest.raises(CommandError):
            self.call('no-such-plan')


class TestAdminHelpTextIsNotPublic:
    """
    The GraphQL schema is what the public UI reads.

    The admin help text is meant for admin users only, so it must not become
    part of any public type, e.g. by being added to a model's `public_fields`.
    """

    def test_not_in_graphql_schema(self):
        from aplans.schema import schema

        assert 'adminHelpText' not in schema.as_str()

    def test_public_help_text_is_in_graphql_schema(self):
        from aplans.schema import schema

        assert 'helpText' in schema.as_str()
