from __future__ import annotations

from typing import cast

import strawberry as sb
import strawberry_django
from django.contrib.contenttypes.models import ContentType
from django.forms import ValidationError
from graphql import GraphQLError
from strawberry import auto
from strawberry_django.fields.types import OperationInfo

from kausal_common.strawberry.errors import NotFoundError, PermissionDeniedError
from kausal_common.strawberry.helpers import get_or_error
from kausal_common.strawberry.permissions import SuperuserOnly
from kausal_common.users import user_or_bust

from aplans import gql

from actions.models import Action, Plan
from actions.models.attributes import AttributeChoice, AttributeType, AttributeTypeChoiceOption
from actions.models.category import Category, CategoryType
from actions.models.features import PlanFeatures
from actions.schema import (
    ActionNode,
    AttributeTypeFormat,
    AttributeTypeNode,
    CategoryNode,
    CategoryTypeNode,
    CategoryTypeSelectWidget,
    PlanNode,
)


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
    short_name: auto
    country: str = sb.field(description='ISO 3166-1 country code (e.g. FI, DE, US)', default='FI')
    primary_language: str = sb.field(
        default='en-US',
        description='Primary language code (ISO 639-1, e.g. "en-US", "fi", "de-CH")',
    )
    other_languages: list[str] = sb.field(
        default_factory=list,
        description='Additional language codes (ISO 639-1)',
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
    plan_id: sb.ID = sb.field(description='The PK or identifier of the plan')
    """The pk or identifier of the plan."""
    organization_id: sb.ID = sb.field(description='The PK of the organization')
    """The pk of the organization."""


@strawberry_django.input(CategoryType)
class CategoryTypeInput:
    plan_id: sb.ID
    identifier: sb.auto
    name: sb.auto
    select_widget: CategoryTypeSelectWidget | None = strawberry_django.field()  # type: ignore[valid-type]  # pyright: ignore[reportInvalidTypeForm]
    usable_for_actions: sb.auto
    usable_for_indicators: sb.auto
    synchronize_with_pages: sb.auto = strawberry_django.field(
        description=(
            'Should a content page hierarchy be automatically generated for the categories. '
            'If not set, defaults to the value of `primaryActionClassification`.'
        )
    )
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


# Mutation classes
@sb.type
class PlanMutations:
    @gql.mutation(
        permission_classes=[SuperuserOnly],
        description='Create a new plan; returns the newly created plan',
    )
    def create_plan(self, info: gql.Info, input: PlanInput) -> PlanNode:
        from actions.models import Plan
        from orgs.models import Organization

        # Get the organization
        org = get_or_error(info, Organization, id=input.organization_id)
        plan = Plan(
            identifier=input.identifier,
            name=input.name,
            primary_language=input.primary_language,
            organization=org,
            other_languages=input.other_languages or [],
            short_name=input.short_name,
            country=input.country,
            theme_identifier=input.theme_identifier or 'default',
        )
        try:
            plan.full_clean()
        except ValidationError as e:
            # We ignore the primary_action_classification error because otherwise
            # it'd be a chicken-and-egg problem.
            e.error_dict.pop('primary_action_classification', None)
            if e.error_dict:
                raise
        plan.apply_defaults(plan)

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

    @gql.mutation(
        permission_classes=[SuperuserOnly], description='Create a new category type; returns the newly created category type'
    )
    def create_category_type(self, info: gql.Info, input: CategoryTypeInput) -> CategoryTypeNode:
        # Get the plan
        plan = get_or_error(info, Plan, input.plan_id)

        if input.primary_action_classification and plan.primary_action_classification is not None:
            raise ValidationError('A plan can only have one primary action classification.')

        category_type, create_args, _ = gql.prepare_create_update(
            info=info, model_or_instance=CategoryType(plan=plan), data=input
        )
        if 'synchronize_with_pages' not in create_args:
            category_type.synchronize_with_pages = input.primary_action_classification
        category_type.editable_for_actions = category_type.usable_for_actions
        category_type.full_clean()
        category_type.save()

        if input.primary_action_classification:
            plan.primary_action_classification = category_type
            plan.save()

        category_type = CategoryType.objects.get(pk=category_type.pk)
        return cast('CategoryTypeNode', category_type)  # pyright: ignore[reportInvalidCast]

    @gql.mutation(permission_classes=[SuperuserOnly], description='Create a new category; returns the newly created category')
    def create_category(self, info: gql.Info, input: CategoryInput) -> CategoryNode:
        # Get the category type
        category_type = get_or_error(info, CategoryType, pk=input.type_id)
        if not category_type.editable_for_actions and not category_type.editable_for_indicators:
            raise ValidationError('Categories of this type are not editable.')

        categories = category_type.categories.all()

        # Get parent if provided
        parent: Category | None = None
        if input.parent_id:
            parent = get_or_error(info, categories, pk=input.parent_id)

        obj = Category(type=category_type, parent=parent)
        if category_type.hide_category_identifiers:
            if input.identifier:
                raise ValidationError({'identifier': 'Category identifiers are not allowed for this category type.'})
            obj.generate_identifier()

        category, _, _ = gql.prepare_create_update(info=info, model_or_instance=obj, data=input)
        if isinstance(input.order, int):
            category.order_on_create = input.order

        category.full_clean()
        category.save()

        return cast('CategoryNode', category)  # pyright: ignore[reportInvalidCast]

    @gql.mutation(permission_classes=[SuperuserOnly])
    def create_attribute_type(self, info: gql.Info, input: AttributeTypeInput) -> AttributeTypeNode:
        from django.contrib.contenttypes.models import ContentType

        from indicators.models import Unit

        data = gql.parse_input(info, input)

        # Get the plan
        user = user_or_bust(info.context.user)
        qs = Plan.objects.qs.visible_for_user(user).by_id_or_identifier(data.pop('plan_id'))
        plan = get_or_error(info, qs)

        # Get content types
        action_ct = ContentType.objects.get_for_model(Action)
        plan_ct = ContentType.objects.get_for_model(Plan)

        # Get unit if provided
        unit: Unit | None = None
        if unit_id := data.pop('unit_id', None):
            unit = get_or_error(info, Unit, pk=unit_id)

        # Create attribute type
        attr_type = AttributeType(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            unit=unit,
            primary_language=plan.primary_language,
            other_languages=plan.other_languages or [],
        )

        attr_type, _, _ = gql.prepare_instance(
            info=info, model_or_instance=attr_type, cleaned_data=data
        )

        format = AttributeType.AttributeFormat(attr_type.format)
        needs_choices = format in (
            AttributeType.AttributeFormat.ORDERED_CHOICE,
            AttributeType.AttributeFormat.UNORDERED_CHOICE,
            AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,
        )

        # Create choice options if provided
        if choice_options := data.get('choice_options') or []:
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

        attr_type.full_clean()
        attr_type.save()

        options = [
            AttributeTypeChoiceOption(
                type=attr_type,
                identifier=choice_option['identifier'],
                name=choice_option['name'],
                order=choice_option['order'],
            )
            for choice_option in choice_options
        ]
        if options:
            AttributeTypeChoiceOption.objects.bulk_create(options)

        attr_type = AttributeType.objects.get(pk=attr_type.pk)
        return cast('AttributeTypeNode', attr_type)  # pyright: ignore[reportInvalidCast]

    @gql.mutation(permission_classes=[SuperuserOnly], description='Delete a recently created plan (must be < 2 days old)')
    def delete_plan(self, info: gql.Info, id: sb.ID) -> OperationInfo | None:
        from datetime import timedelta

        from django.utils import timezone

        plan = gql.get_plan_or_error(info, id)
        max_age = timedelta(days=2)
        if timezone.now() - plan.created_at > max_age:
            raise PermissionDeniedError(
                info,
                f'Can only delete plans created within the last 2 days. This plan was created on {plan.created_at.date()}.',
            )

        plan.delete()
        return None

    @gql.mutation(permission_classes=[SuperuserOnly], description='Add a related organization to a plan')
    def add_related_organization(self, info: gql.Info, input: AddRelatedOrganizationInput) -> PlanNode:
        from orgs.models import Organization

        # Get the plan and organization
        plan = gql.get_plan_or_error(info, input.plan_id)
        user = user_or_bust(info.context.user)
        if not user.is_general_admin_for_plan(plan):
            raise PermissionDeniedError(info, 'Allowed only for general admins of the plan')

        organization = get_or_error(info, Organization, pk=input.organization_id)

        # Add the organization to the plan's related organizations
        plan.related_organizations.add(organization)

        return cast('PlanNode', plan)  # pyright: ignore[reportInvalidCast]


@sb.type
class ActionMutations:
    def _set_action_categories(self, info: gql.Info, action: Action, category_ids: list[sb.ID]) -> None:
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
                raise NotFoundError(info, f'Category {cat_id} does not belong to plan {plan.identifier}.')
            cats_by_type.setdefault(cat_obj.type, []).append(cat_obj)

        for cat_type, cats in cats_by_type.items():
            if cat_type.select_widget == cat_type.SelectWidget.SINGLE and len(cats) > 1:
                raise ValidationError(
                    f'Only one category can be assigned to a single-select category type (identifier: {cat_type.identifier}).',
                )
            action.set_categories(cat_type, list[Category | int](cats))

    def _set_action_choice_attributes(
        self, info: gql.Info, action: Action, attribute_values: list[ActionAttributeValueInput]
    ) -> None:
        action_ct = ContentType.objects.get_for_model(Action)
        plan = action.plan
        for attr_val in attribute_values:
            attr_type = plan.action_attribute_types.filter(pk=attr_val.attribute_type_id).first()
            if attr_type is None:
                raise GraphQLError(
                    f'Attribute type {attr_val.attribute_type_id} does not belong to plan {plan.identifier} or '
                    'is not usable for actions.',
                    nodes=info.field_nodes,
                )
            choice = AttributeTypeChoiceOption.objects.get(pk=attr_val.choice_id, type=attr_type)
            AttributeChoice.objects.create(
                type=attr_type,
                content_type=action_ct,
                object_id=action.pk,
                choice=choice,
            )

    def _create_action_m2m(self, info: gql.Info, action: Action, input: ActionInput) -> None:
        # Assign categories
        if input.category_ids:
            self._set_action_categories(info, action, input.category_ids)

        # Assign choice attributes
        if input.attribute_values:
            self._set_action_choice_attributes(info, action, input.attribute_values)

    @gql.mutation(permission_classes=[SuperuserOnly])
    def create_action(self, info: gql.Info, input: ActionInput) -> ActionNode:
        from actions.models import Action, Plan
        from orgs.models import Organization

        # Get the plan
        plan = Plan.objects.get(pk=input.plan_id)

        if plan.actions_locked:
            raise PermissionDeniedError(info, 'Actions are locked for this plan.')

        # Get primary org if provided
        primary_org: Organization | None = None
        if input.primary_org_id:
            primary_org = get_or_error(info, Organization, pk=input.primary_org_id)

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

        self._create_action_m2m(info, action, input)

        action = Action.objects.get(pk=action.pk)
        return cast('ActionNode', action)  # pyright: ignore[reportInvalidCast]
