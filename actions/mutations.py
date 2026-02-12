from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast

import strawberry as sb
import strawberry_django
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from strawberry import auto
from strawberry.extensions import FieldExtension
from strawberry.types.unset import UnsetType

from kausal_common.users import user_or_bust, user_or_none

from actions.models import Action, Plan
from actions.models.attributes import AttributeChoice, AttributeType, AttributeTypeChoiceOption
from actions.models.category import Category, CategoryType
from actions.models.features import PlanFeatures
from actions.schema import (  # noqa: TC001
    ActionNode,
    AttributeTypeFormat,
    AttributeTypeNode,
    CategoryNode,
    CategoryTypeNode,
    PlanNode,
)

if TYPE_CHECKING:
    from aplans.graphql_types import SBInfo

    from orgs.models import Organization


@strawberry_django.input(PlanFeatures)
class PlanFeaturesInput:
    has_action_identifiers: auto
    has_action_official_name: auto
    has_action_lead_paragraph: auto
    has_action_primary_orgs: auto


# Input types
@strawberry_django.input(Plan)
class PlanInput:
    name: auto
    identifier: auto
    organization_id: sb.ID
    primary_language: str = sb.field(
        default='en-US',
        description='Primary language code (ISO 639-1, e.g. "en-US", "fi", "de-CH").',
    )
    short_name: auto
    other_languages: list[str] = sb.field(
        default_factory=list,
        description='Additional language codes (ISO 639-1).',
    )
    theme_identifier: auto
    features: PlanFeaturesInput | None = None


@sb.input
class ActionAttributeValueInput:
    attribute_type_id: sb.ID
    choice_id: sb.ID


@strawberry_django.input(Action)
class ActionInput:
    name: sb.auto
    plan_id: sb.auto
    identifier: sb.auto
    description: sb.auto
    primary_org_id: sb.auto
    category_ids: list[sb.ID] | None = None
    attribute_values: list[ActionAttributeValueInput] | None = None


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
    hide_category_identifiers: sb.auto
    primary_action_classification: bool = sb.field(
        description=(
            'Whether this category type is the primary action classification. '
            'NOTE: A Plan must have exactly one primary action classification.'
        ),
        default=False,
    )


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
    format: AttributeTypeFormat  # type: ignore[valid-type]  # pyright: ignore[reportInvalidTypeForm]
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


def _strip_unset(**kwargs: Any) -> dict[str, Any]:
    """Remove strawberry UNSET values from keyword arguments."""
    return {k: v for k, v in kwargs.items() if not isinstance(v, UnsetType)}


# Mutation classes
@sb.type
class PlanMutations:
    @sb.mutation(extensions=[PlanAdminOnlyMutation()], description='Create a new plan. Returns the newly created plan.')
    def create_plan(self, input: PlanInput) -> PlanNode:
        from actions.models import Plan
        from orgs.models import Organization

        # Get the organization
        org: Organization = Organization.objects.get(pk=input.organization_id)

        short_name = None if isinstance(input.short_name, UnsetType) else input.short_name
        theme_identifier = None if isinstance(input.theme_identifier, UnsetType) else input.theme_identifier

        # Create plan with defaults
        plan = Plan.create_with_defaults(
            identifier=input.identifier,
            name=input.name,
            primary_language=input.primary_language,
            organization=org,
            other_languages=input.other_languages or None,
            short_name=short_name,
        )

        # Set theme if provided
        if theme_identifier:
            plan.theme_identifier = theme_identifier
        else:
            plan.theme_identifier = 'default'
        plan.save()

        # Apply feature flags if provided
        if input.features is not None:
            features = plan.features
            for field_name in (
                'has_action_identifiers',
                'has_action_official_name',
                'has_action_lead_paragraph',
                'has_action_primary_orgs',
            ):
                val = getattr(input.features, field_name)
                if isinstance(val, bool):
                    setattr(features, field_name, val)
            features.save()

        return cast('PlanNode', plan)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(
        extensions=[PlanAdminOnlyMutation()], description='Create a new category type. Returns the newly created category type.'
    )
    @transaction.atomic
    def create_category_type(self, input: CategoryTypeInput) -> CategoryTypeNode:
        # Get the plan
        plan = Plan.objects.get(pk=input.plan_id)

        if input.primary_action_classification and plan.primary_action_classification is not None:
            raise ValidationError('A plan can only have one primary action classification.')

        # Create category type. For new plans, default editability to match usability --
        # it doesn't make sense to restrict editing before categories exist. Editability
        # can be tightened later via an update mutation.
        category_type = CategoryType.objects.create(
            plan=plan,
            identifier=input.identifier,
            name=input.name,
            **_strip_unset(
                select_widget=input.select_widget,
                usable_for_actions=input.usable_for_actions,
                usable_for_indicators=input.usable_for_indicators,
                editable_for_actions=input.usable_for_actions,  # initially has to be editable if usable
                editable_for_indicators=input.usable_for_indicators,  # initially has to be editable if usable
                hide_category_identifiers=input.hide_category_identifiers,
            ),
        )

        if input.primary_action_classification:
            plan.primary_action_classification = category_type
            plan.save()

        category_type = CategoryType.objects.get(pk=category_type.pk)
        return cast('CategoryTypeNode', category_type)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(extensions=[PlanAdminOnlyMutation()], description='Create a new category. Returns the newly created category.')
    @transaction.atomic
    def create_category(self, input: CategoryInput) -> CategoryNode:
        # Get the category type
        category_type = CategoryType.objects.get(pk=input.type_id)

        if not category_type.editable_for_actions and not category_type.editable_for_indicators:
            raise ValidationError('Categories of this type are not editable.')

        # Get parent if provided
        parent: Category | None = None
        if input.parent_id and not isinstance(input.parent_id, UnsetType):
            parent = Category.objects.get(type=category_type, pk=input.parent_id)

        # Create category
        category = Category(
            type=category_type,
            identifier=input.identifier,
            name=input.name,
            parent=parent,
        )

        if isinstance(input.order, int):
            category.order_on_create = input.order

        category.full_clean()
        category.save()

        return cast('CategoryNode', category)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(extensions=[PlanAdminOnlyMutation()])
    @transaction.atomic
    def create_attribute_type(self, info: SBInfo, input: AttributeTypeInput) -> AttributeTypeNode:
        from django.contrib.contenttypes.models import ContentType

        from indicators.models import Unit

        # Get the plan
        user = user_or_bust(info.context.user)
        plan = Plan.objects.qs.visible_for_user(user).by_id_or_identifier(input.plan_id).get()

        # Get content types
        action_ct = ContentType.objects.get_for_model(Action)
        plan_ct = ContentType.objects.get_for_model(Plan)

        # Get unit if provided
        unit: Unit | None = None
        if input.unit_id:
            unit = Unit.objects.get(pk=input.unit_id)

        format_value: str = getattr(input.format, 'value')  # noqa: B009
        format = AttributeType.AttributeFormat(format_value)
        needs_choices = format in (
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
        elif needs_choices:
            raise ValidationError(
                'Choice options are required for ordered choice, unordered choice,'
                ' and optional choice with optional text attributes.'
            )

        # Create attribute type
        attr_type = AttributeType(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            identifier=input.identifier,
            name=input.name,
            format=format,
            help_text=input.help_text or '',
            unit=unit,
            primary_language=plan.primary_language,
            other_languages=plan.other_languages or [],
        )
        attr_type.full_clean()
        attr_type.save()

        for choice_option in input.choice_options or []:
            AttributeTypeChoiceOption.objects.create(
                type=attr_type,
                identifier=choice_option.identifier,
                name=choice_option.name,
                order=choice_option.order,
            )

        attr_type = AttributeType.objects.get(pk=attr_type.pk)
        return cast('AttributeTypeNode', attr_type)  # pyright: ignore[reportInvalidCast]

    @sb.mutation(extensions=[PlanAdminOnlyMutation()], description='Delete a recently created plan (must be < 2 days old)')
    def delete_plan(self, id: sb.ID) -> bool:
        from datetime import timedelta

        from django.utils import timezone

        plan = Plan.objects.qs.by_id_or_identifier(id).first()
        if plan is None:
            raise ValidationError('Plan not found.')

        max_age = timedelta(days=2)
        if timezone.now() - plan.created_at > max_age:
            raise ValidationError(
                f'Can only delete plans created within the last 2 days. This plan was created on {plan.created_at.date()}.'
            )

        plan.delete()
        return True

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
    def _set_action_categories(self, action: Action, category_ids: list[sb.ID]) -> None:
        plan = action.plan
        ct_qs = plan.category_types.filter(editable_for_actions=True)
        cts_by_id = {ct.id: ct for ct in ct_qs}
        cats_by_id = {cat.id: cat for cat in Category.objects.filter(type__in=ct_qs)}
        for cat in cats_by_id.values():
            cat.type = cts_by_id[cat.type_id]

        cats_by_type: dict[CategoryType, list[Category]] = {}
        for cat_id in category_ids:
            cat_obj = cats_by_id.get(int(cat_id))
            if cat_obj is None:
                raise ValidationError(f'Category {cat_id} does not belong to plan {plan.identifier}.')
            cats_by_type.setdefault(cat_obj.type, []).append(cat_obj)

        for cat_type, cats in cats_by_type.items():
            if cat_type.select_widget == cat_type.SelectWidget.SINGLE and len(cats) > 1:
                raise ValidationError(
                    f'Only one category can be assigned to a single-select category type (identifier: {cat_type.identifier}).'
                )
            action.set_categories(cat_type, list(cats))

    def _set_action_choice_attributes(self, action: Action, attribute_values: list[ActionAttributeValueInput]) -> None:
        action_ct = ContentType.objects.get_for_model(Action)
        plan = action.plan
        for attr_val in attribute_values:
            attr_type = plan.action_attribute_types.filter(pk=attr_val.attribute_type_id).first()
            if attr_type is None:
                raise ValidationError(
                    f'Attribute type {attr_val.attribute_type_id} does not belong to plan {plan.identifier} or '
                    'is not usable for actions.'
                )
            choice = AttributeTypeChoiceOption.objects.get(pk=attr_val.choice_id, type=attr_type)
            AttributeChoice.objects.create(
                type=attr_type,
                content_type=action_ct,
                object_id=action.pk,
                choice=choice,
            )

    def _create_action_m2m(self, action: Action, input: ActionInput) -> None:
        # Assign categories
        if input.category_ids:
            self._set_action_categories(action, input.category_ids)

        # Assign choice attributes
        if input.attribute_values:
            self._set_action_choice_attributes(action, input.attribute_values)

    @sb.mutation(extensions=[PlanAdminOnlyMutation()])
    @transaction.atomic
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

        action.full_clean()
        action.save()

        self._create_action_m2m(action, input)

        action = Action.objects.get(pk=action.pk)
        return cast('ActionNode', action)  # pyright: ignore[reportInvalidCast]
