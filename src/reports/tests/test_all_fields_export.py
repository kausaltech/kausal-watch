from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType

import pytest

from actions.models import Action, AttributeType
from actions.tests.factories import AttributeTypeFactory, CategoryTypeFactory
from people.tests.factories import PersonFactory
from reports.models import ReportType
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db

VisibleFor = AttributeType.VisibleFor


def action_attribute_type(plan: Plan, visible_for: str) -> AttributeType:
    return AttributeTypeFactory.create(
        object_content_type=ContentType.objects.get_for_model(Action),
        scope=plan,
        instances_visible_for=visible_for,
        format=AttributeType.AttributeFormat.TEXT,
    )


def public_site_viewer(plan: Plan) -> User:
    user = UserFactory.create()
    person = PersonFactory.create(user=user)
    plan.public_site_viewers.create(person=person)
    return user


def plan_admin(plan: Plan) -> User:
    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[plan])
    return user


def exported_block_types(report_type: ReportType) -> list[str]:
    return [child.block_type for child in report_type.fields]


def exported_attribute_type_ids(report_type: ReportType) -> set[int]:
    return {child.value['attribute_type'].pk for child in report_type.fields if child.block_type == 'attribute'}


def exported_category_type_ids(report_type: ReportType) -> set[int]:
    return {child.value['category_type'].pk for child in report_type.fields if child.block_type == 'categories'}


class TestGenerateForPlanAllFields:
    def test_includes_fields_that_are_not_dashboard_columns(self, plan_with_pages):
        plan = plan_with_pages
        report_type = ReportType.generate_for_plan_all_fields(plan, plan_admin(plan))
        block_types = exported_block_types(report_type)
        for field in ('implementation_phase', 'status', 'description', 'tasks', 'start_date', 'end_date', 'updated_at'):
            assert field in block_types

    def test_includes_category_types_usable_for_actions(self, plan_with_pages):
        plan = plan_with_pages
        usable = CategoryTypeFactory.create(plan=plan, usable_for_actions=True)
        not_usable = CategoryTypeFactory.create(plan=plan, usable_for_actions=False)
        report_type = ReportType.generate_for_plan_all_fields(plan, plan_admin(plan))
        category_type_ids = exported_category_type_ids(report_type)
        assert usable.pk in category_type_ids
        assert not_usable.pk not in category_type_ids

    def test_excludes_attribute_types_of_other_plans(self, plan_with_pages, plan_factory):
        plan = plan_with_pages
        other = action_attribute_type(plan_factory(), VisibleFor.PUBLIC)
        report_type = ReportType.generate_for_plan_all_fields(plan, plan_admin(plan))
        assert other.pk not in exported_attribute_type_ids(report_type)

    @pytest.mark.parametrize(
        ('visible_for', 'viewer_sees', 'admin_sees'),
        [
            (VisibleFor.PUBLIC, True, True),
            (VisibleFor.AUTHENTICATED, True, True),
            (VisibleFor.CONTACT_PERSONS, False, True),
            (VisibleFor.MODERATORS, False, True),
            (VisibleFor.PLAN_ADMINS, False, True),
        ],
    )
    def test_attribute_types_are_filtered_by_visibility(self, plan_with_pages, visible_for, viewer_sees, admin_sees):
        plan = plan_with_pages
        attribute_type = action_attribute_type(plan, visible_for)

        viewer_report_type = ReportType.generate_for_plan_all_fields(plan, public_site_viewer(plan))
        admin_report_type = ReportType.generate_for_plan_all_fields(plan, plan_admin(plan))

        assert (attribute_type.pk in exported_attribute_type_ids(viewer_report_type)) is viewer_sees
        assert (attribute_type.pk in exported_attribute_type_ids(admin_report_type)) is admin_sees


def test_full_export_contains_categories_and_non_public_attributes_for_plan_admin(plan_with_pages):
    from actions.tests.factories import ActionFactory, AttributeTextFactory, CategoryFactory
    from reports.export import export_dashboard_report_for_plan

    plan = plan_with_pages
    category_type = CategoryTypeFactory.create(plan=plan, usable_for_actions=True)
    category = CategoryFactory.create(type=category_type, name='Exported category')
    attribute_type = action_attribute_type(plan, VisibleFor.PLAN_ADMINS)
    action = ActionFactory.create(plan=plan)
    action.categories.add(category)
    action.save()
    AttributeTextFactory.create(type=attribute_type, content_object=action, text='Internal note')

    output, _filename = export_dashboard_report_for_plan(plan, 'csv', plan_admin(plan), all_fields=True)

    assert isinstance(output, str)
    assert 'Exported category' in output
    assert 'Internal note' in output

    viewer_output, _filename = export_dashboard_report_for_plan(plan, 'csv', public_site_viewer(plan), all_fields=True)

    assert isinstance(viewer_output, str)
    assert 'Exported category' in viewer_output
    assert 'Internal note' not in viewer_output
