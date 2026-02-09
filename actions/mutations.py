from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast

import strawberry as sb
import strawberry_django
from strawberry.extensions import FieldExtension

from kausal_common.users import user_or_bust, user_or_none

from actions.models import Action, Plan
from actions.models.attributes import AttributeType, AttributeTypeChoiceOption
from actions.models.category import Category, CategoryType
from actions.models.features import PlanFeatures
from actions.schema import ActionNode, AttributeTypeNode, CategoryNode, CategoryTypeNode, PlanNode  # noqa: TC001

if TYPE_CHECKING:
    from aplans.graphql_types import SBInfo

    from orgs.models import Organization


@strawberry_django.input(PlanFeatures)
class PlanFeaturesInput:
    has_action_identifiers: sb.auto
    has_action_official_name: sb.auto
    has_action_lead_paragraph: sb.auto
    has_action_primary_orgs: sb.auto


# Input types
@strawberry_django.input(Plan)
class PlanInput:
    name: sb.auto
    identifier: sb.auto
    primary_language: sb.auto
    organization_id: sb.ID
    short_name: sb.auto
    other_languages: sb.auto
    theme_identifier: sb.auto
    features: PlanFeaturesInput | None = None


@strawberry_django.input(Action)
class ActionInput:
    name: sb.auto
    plan_id: sb.auto
    identifier: sb.auto
    description: sb.auto
    primary_org_id: sb.auto


@sb.input
class ChoiceOptionInput:
    identifier: str
    name: str
    order: int


@sb.input
class AddRelatedOrganizationInput:
    plan_id: sb.ID = sb.field(description='The pk or identifier of the plan.')
    """The pk or identifier of the plan."""
    organization_id: sb.ID = sb.field(description='The pk of the organization.')
    """The pk of the organization."""


@strawberry_django.input(CategoryType)
class CategoryTypeInput:
    plan_id: sb.ID
    identifier: sb.auto
    name: sb.auto
    select_widget: sb.auto
    usable_for_actions: sb.auto
    usable_for_indicators: sb.auto
    editable_for_actions: sb.auto
    hide_category_identifiers: sb.auto


@strawberry_django.input(Category)
class CategoryInput:
    type_id: sb.ID
    identifier: sb.auto
    name: sb.auto
    parent_id: sb.ID | None = None
    order: sb.auto


@strawberry_django.input(AttributeType)
class AttributeTypeInput:
    plan_id: sb.ID
    identifier: sb.auto
    name: sb.auto
    format: sb.auto
    help_text: sb.auto
    unit_id: sb.ID | None = None
    choice_options: list[ChoiceOptionInput] | None = None


class AuthenticationRequiredError(PermissionError):
    pass


class PlanAdminOnlyMutation(FieldExtension):
    def resolve(self, next_: Callable[..., Any], source: Any, info: SBInfo, **kwargs: Any) -> Any:
        user = user_or_none(info.context.user)
        if user is None:
            raise PermissionError('Authentication required for this operation.')
        # Only superusers for now
        if not user.is_superuser:
            raise PermissionError('Superuser required for this operation.')
        return next_(source, info, **kwargs)


class ValidationError(Exception):
    pass


# Mutation classes
@sb.type
class PlanMutations:
    @sb.mutation(extensions=[PlanAdminOnlyMutation()], description='Create a new plan')
    def create_plan(self, input: PlanInput) -> PlanNode:
        from actions.models import Plan
        from orgs.models import Organization

        # Get the organization
        org: Organization = Organization.objects.get(pk=input.organization_id)

        # Create plan with defaults
        plan = Plan.create_with_defaults(
            identifier=input.identifier,
            name=input.name,
            primary_language=input.primary_language,
            organization=org,
            other_languages=input.other_languages,
            short_name=input.short_name,
        )

        # Set theme if provided
        if input.theme_identifier:
            plan.theme_identifier = input.theme_identifier
            plan.save()

        return cast('PlanNode', plan)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(extensions=[PlanAdminOnlyMutation()])
    def create_category_type(self, input: CategoryTypeInput) -> CategoryTypeNode:
        # Get the plan
        plan: Plan = Plan.objects.get(pk=input.plan_id)

        # Create category type. For new plans, default editability to match usability --
        # it doesn't make sense to restrict editing before categories exist. Editability
        # can be tightened later via an update mutation.
        category_type = CategoryType.objects.create(
            plan=plan,
            identifier=input.identifier,
            name=input.name,
            select_widget=input.select_widget,
            usable_for_actions=input.usable_for_actions,
            usable_for_indicators=input.usable_for_indicators,
            editable_for_actions=input.usable_for_actions,
            editable_for_indicators=input.usable_for_indicators,
            hide_category_identifiers=input.hide_category_identifiers,
        )

        return cast('CategoryTypeNode', category_type)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(extensions=[PlanAdminOnlyMutation()])
    def create_category(self, input: CategoryInput) -> CategoryNode:
        # Get the category type
        category_type: CategoryType = CategoryType.objects.get(pk=input.type_id)

        # Get parent if provided
        parent: Category | None = None
        if input.parent_id:
            parent = Category.objects.get(pk=input.parent_id)

        if not category_type.editable_for_actions and not category_type.editable_for_indicators:
            raise ValidationError('Categories of this type are not editable.')

        # Create category
        category = Category(
            type=category_type,
            identifier=input.identifier,
            name=input.name,
            parent=parent,
        )

        if input.order is not None:
            category.order_on_create = input.order

        category.save()

        return cast('CategoryNode', category)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(extensions=[PlanAdminOnlyMutation()])
    def create_attribute_type(self, input: AttributeTypeInput) -> AttributeTypeNode:
        from django.contrib.contenttypes.models import ContentType

        from indicators.models import Unit

        # Get the plan
        plan = Plan.objects.get(pk=input.plan_id)

        # Get content types
        action_ct = ContentType.objects.get_for_model(Action)
        plan_ct = ContentType.objects.get_for_model(Plan)

        # Get unit if provided
        unit: Unit | None = None
        if input.unit_id:
            unit = Unit.objects.get(pk=input.unit_id)

        # Create attribute type
        attr_type = AttributeType.objects.create(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            identifier=input.identifier,
            name=input.name,
            format=input.format,
            help_text=input.help_text or '',
            unit=unit,
            primary_language=plan.primary_language,
            other_languages=plan.other_languages or [],
        )

        needs_choices = attr_type.format in (
            AttributeType.AttributeFormat.ORDERED_CHOICE,
            AttributeType.AttributeFormat.UNORDERED_CHOICE,
            AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,
        )

        # Create choice options if provided
        if input.choice_options:
            if not needs_choices:
                raise ValidationError(
                    'Choice options are only allowed for ordered choice, unordered choice,'
                    ' and optional choice with optional text attributes.'
                )
            for choice_option in input.choice_options:
                AttributeTypeChoiceOption.objects.create(
                    type=attr_type,
                    identifier=choice_option.identifier,
                    name=choice_option.name,
                    order=choice_option.order,
                )
        elif needs_choices:
            raise ValidationError(
                'Choice options are required for ordered choice, unordered choice,'
                ' and optional choice with optional text attributes.'
            )

        return cast('AttributeTypeNode', attr_type)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(extensions=[PlanAdminOnlyMutation()], description='Add a related organization to a plan')
    def add_related_organization(self, info: SBInfo, input: AddRelatedOrganizationInput) -> PlanNode:
        from orgs.models import Organization

        # Get the plan and organization
        plan = Plan.objects.qs.by_id_or_identifier(input.plan_id).first()
        if plan is None:
            raise ValidationError('Plan not found.')
        user = user_or_bust(info.context.user)
        if not user.is_general_admin_for_plan(plan):
            raise PermissionError('Allowed only for general admins of the plan.')

        organization = Organization.objects.get(pk=input.organization_id)

        # Add the organization to the plan's related organizations
        plan.related_organizations.add(organization)

        return cast('PlanNode', plan)  # pyright: ignore[reportInvalidCast]


@sb.type
class ActionMutations:
    @sb.mutation(extensions=[PlanAdminOnlyMutation()])
    def create_action(self, input: ActionInput) -> ActionNode:
        from actions.models import Action, Plan
        from orgs.models import Organization

        # Get the plan
        plan = Plan.objects.get(pk=input.plan_id)

        if plan.actions_locked:
            raise PermissionError('Actions are locked for this plan.')

        # Get primary org if provided
        primary_org: Organization | None = None
        if input.primary_org_id:
            primary_org = Organization.objects.get(pk=input.primary_org_id)

        # Create action
        action = Action(
            plan=plan,
            name=input.name,
            description=input.description or '',
            primary_org=primary_org,
        )

        # Generate or use provided identifier
        if input.identifier:
            if not plan.features.has_action_identifiers:
                raise ValidationError('Action identifiers are not enabled for this plan.')
            action.identifier = input.identifier
        else:
            if plan.features.has_action_identifiers:
                raise ValidationError('Action identifier required for this plan.')
            action.generate_identifier()

        action.save()

        return cast('ActionNode', action)  # pyright: ignore[reportInvalidCast]
