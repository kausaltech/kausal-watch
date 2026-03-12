from __future__ import annotations

from typing import TYPE_CHECKING, cast

import strawberry as sb
import strawberry_django
from django.contrib.contenttypes.models import ContentType
from django.forms import ValidationError

from kausal_common.strawberry.errors import NotFoundError, PermissionDeniedError
from kausal_common.strawberry.helpers import get_or_error
from kausal_common.strawberry.permissions import SuperuserOnly

from aplans import gql

from actions.models import (
    Action,
    ActionLink,
    ActionResponsibleParty,
    AttributeCategoryChoice,
    AttributeChoiceWithText,
    AttributeText,
)
from actions.models.attributes import AttributeChoice, AttributeRichText, AttributeType, AttributeTypeChoiceOption
from actions.models.category import Category
from actions.schema import (
    ActionNode,
)
from orgs.models import Organization

if TYPE_CHECKING:
    from collections.abc import Sequence

    from actions.models.category import CategoryType


@sb.type(description='Result of a bulk action update')
class BulkUpdateActionsResult:
    count: int = sb.field(description='Number of actions updated')
    ids: list[sb.ID] = sb.field(description='IDs of updated actions')


@sb.input
class AttributeValueChoiceInput:
    choice_id: sb.ID | None
    text: sb.Maybe[str] = None


@sb.input(one_of=True, description='Value for an attribute (choose one based on attribute type format)')
class ActionAttributeValueInput:
    choice: sb.Maybe[AttributeValueChoiceInput] = sb.field(
        description='Choice value (pk + optional rich text explanation) for an attribute', default=None
    )
    rich_text: sb.Maybe[str] = sb.field(description='HTML rich text value for an attribute', default=None)
    text: sb.Maybe[str] = sb.field(description='Plain text value for an attribute', default=None)
    category_choices: sb.Maybe[list[sb.ID]] = sb.field(description='Category choice values (pks) for an attribute', default=None)


@sb.input
class ActionAttributeUpdateInput:
    attribute_type_id: sb.ID = sb.field(description='ID (PK or identifier) of the attribute type')
    value: ActionAttributeValueInput


@sb.input(description='Rich text attribute value for an action')
class ActionRichTextAttributeInput:
    attribute_type_id: sb.ID = sb.field(description='ID of the attribute type')
    value: str = sb.field(description='HTML rich text value')


@sb.input(description='Responsible party assignment for an action')
class ActionResponsiblePartyInput:
    organization_id: sb.ID = sb.field(description='ID of the organization')
    role: ActionResponsibleParty.Role | None = sb.field(
        default=ActionResponsibleParty.Role.PRIMARY,
        description='Role of this organization in implementing the action.',
    )


@sb.input(description='Link to associate with an action')
class ActionLinkInput:
    url: str = sb.field(description='URL of the link')
    title: str = sb.field(default='', description='Display title for the link')


@strawberry_django.input(Action)
class ActionInput:
    plan_id: sb.auto
    name: sb.auto
    identifier: sb.auto
    lead_paragraph: sb.auto
    description: sb.auto
    primary_org_id: sb.auto
    category_ids: list[sb.ID] | None
    responsible_parties: list[ActionResponsiblePartyInput] | None
    links: list[ActionLinkInput] | None
    attribute_values: list[ActionAttributeUpdateInput] | None


@strawberry_django.input(
    Action, description='Update input for a single action in a bulk update', partial=True
)
class ActionUpdateInput:
    id: sb.ID = sb.field(description='The action ID (pk)')
    name: sb.auto
    identifier: sb.auto
    description: sb.auto
    lead_paragraph: sb.auto
    primary_org_id: sb.auto
    category_ids: list[sb.ID] | None
    responsible_parties: list[ActionResponsiblePartyInput] | None
    links: list[ActionLinkInput] | None
    attribute_values: list[ActionAttributeUpdateInput] | None


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

    def _set_action_attributes(
        self,
        info: gql.Info,
        action: Action,
        attribute_values: Sequence[ActionAttributeUpdateInput],
        for_create: bool = False,
    ) -> None:
        plan = action.plan
        attr_types = list(plan.action_attribute_types.all())
        attr_types_by_id = {str(attr_type.id): attr_type for attr_type in attr_types}
        attr_types_by_identifier = {attr_type.identifier: attr_type for attr_type in attr_types}

        for attr_input in attribute_values:
            attr_ref = str(attr_input.attribute_type_id)
            attr_type = attr_types_by_id.get(attr_ref) or attr_types_by_identifier.get(attr_ref)
            if attr_type is None:
                raise NotFoundError(
                    info, f'Attribute type {attr_ref} does not exist in plan {plan.identifier}.'
                )

            self._set_action_attribute(info, action, attr_type, attr_input.value, for_create=for_create)

    def _set_action_attribute(
        self, info: gql.Info, action: Action, attr_type: AttributeType, value: ActionAttributeValueInput, for_create: bool = False
    ) -> None:
        if attr_type.format in (
            AttributeType.AttributeFormat.ORDERED_CHOICE,
            AttributeType.AttributeFormat.UNORDERED_CHOICE,
            AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,
        ):
            if value.choice is None:
                raise ValidationError(f'Choice is required for attribute type {attr_type.identifier}.')
            self._set_action_choice_attribute(info, action, attr_type, value.choice.value, for_create=for_create)
        elif attr_type.format == AttributeType.AttributeFormat.RICH_TEXT:
            if value.rich_text is None:
                raise ValidationError(f'Rich text is required for attribute type {attr_type.identifier}.')
            self._set_action_rich_text_attribute(info, action, attr_type, value.rich_text.value, for_create=for_create)
        elif attr_type.format == AttributeType.AttributeFormat.TEXT:
            if value.text is None:
                raise ValidationError(f'Text is required for attribute type {attr_type.identifier}.')
            self._set_action_text_attribute(info, action, attr_type, value.text.value, for_create=for_create)
        elif attr_type.format == AttributeType.AttributeFormat.CATEGORY_CHOICE:
            if value.category_choices is None:
                raise ValidationError(f'Category choices are required for attribute type {attr_type.identifier}.')
            self._set_action_category_choice_attribute(
                info, action, attr_type, value.category_choices.value, for_create=for_create
            )
        else:
            raise NotImplementedError()

    def _set_action_category_choice_attribute(
        self, info: gql.Info, action: Action, attribute_type: AttributeType, values: list[sb.ID], for_create: bool = False
    ) -> None:
        action_ct = ContentType.objects.get_for_model(Action)
        kwargs = dict(type=attribute_type, content_type=action_ct, object_id=action.pk)
        ct = attribute_type.attribute_category_type
        assert ct is not None
        cats_by_id = {cat.id: cat for cat in ct.categories.all()}
        existing = AttributeCategoryChoice.objects.filter(**kwargs).first()
        if existing is not None:
            if for_create:
                raise ValidationError(f'Attribute type {attribute_type.identifier} already has a category choice value.')
            obj = existing
        else:
            obj = AttributeCategoryChoice(**kwargs)
        cat_objs: list[Category] = []
        for cat_id in values:
            cat_obj = cats_by_id.get(int(cat_id))
            if cat_obj is None:
                raise NotFoundError(info, f'Category {cat_id} does not belong to category type {ct.identifier}.')
            cat_objs.append(cat_obj)
        obj.categories.set(cat_objs)
        obj.full_clean()
        obj.save()

    def _set_action_rich_text_attribute(
        self, info: gql.Info, action: Action, attribute_type: AttributeType, value: str, for_create: bool = False
    ) -> None:
        action_ct = ContentType.objects.get_for_model(Action)
        kwargs = dict(type=attribute_type, content_type=action_ct, object_id=action.pk)
        existing = AttributeRichText.objects.filter(**kwargs).first()
        if existing is not None:
            if for_create:
                raise ValidationError(f'Attribute type {attribute_type.identifier} already has a rich text value.')
            obj = existing
        else:
            obj = AttributeRichText(**kwargs)
        obj.text = value
        obj.full_clean()
        obj.save()

    def _set_action_text_attribute(
        self, info: gql.Info, action: Action, attribute_type: AttributeType, value: str, for_create: bool = False
    ) -> None:
        action_ct = ContentType.objects.get_for_model(Action)
        kwargs = dict(type=attribute_type, content_type=action_ct, object_id=action.pk)
        existing = AttributeText.objects.filter(**kwargs).first()
        if existing is not None:
            if for_create:
                raise ValidationError(f'Attribute type {attribute_type.identifier} already has a text value.')
            obj = existing
        else:
            obj = AttributeText(**kwargs)
        obj.text = value
        obj.full_clean()
        obj.save()

    def _set_action_choice_attribute(
        self,
        info: gql.Info,
        action: Action,
        attribute_type: AttributeType,
        value: AttributeValueChoiceInput,
        for_create: bool = False,
    ) -> None:
        action_ct = ContentType.objects.get_for_model(Action)
        if value.choice_id is not None:
            choice_obj = AttributeTypeChoiceOption.objects.get(pk=value.choice_id, type=attribute_type)
        else:
            choice_obj = None
        kwargs = dict(type=attribute_type, content_type=action_ct, object_id=action.pk)
        obj: AttributeChoice | AttributeChoiceWithText
        if attribute_type.format == AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            existing_act = AttributeChoiceWithText.objects.filter(**kwargs).first()
            if existing_act is not None:
                if for_create:
                    raise ValidationError(f'Attribute type {attribute_type.identifier} already has a choice value.')
                act_obj = existing_act
            else:
                act_obj = AttributeChoiceWithText(**kwargs)
            act_obj.choice = choice_obj
            act_obj.text = value.text.value if value.text is not None else ''
            obj = act_obj
        else:
            existing_ac = AttributeChoice.objects.filter(**kwargs).first()
            if existing_ac is not None:
                if for_create:
                    raise ValidationError(f'Attribute type {attribute_type.identifier} already has a choice value.')
                ac_obj = existing_ac
            else:
                ac_obj = AttributeChoice(**kwargs)
            if not choice_obj:
                raise ValidationError(f'Choice is required for attribute type {attribute_type.identifier}.')
            ac_obj.choice = choice_obj
            obj = ac_obj
        obj.full_clean()
        obj.save()

    def _set_action_responsible_parties(self, info: gql.Info, action: Action, parties: list[ActionResponsiblePartyInput]) -> None:
        plan = action.plan
        plan_orgs_by_id = {str(org.id): org for org in Organization.objects.qs.available_for_plan(plan)}
        # Clear existing responsible parties
        action.responsible_parties.all().delete()

        for i, party in enumerate(parties):
            org = plan_orgs_by_id.get(party.organization_id)
            if org is None:
                raise NotFoundError(info, f'Organization {party.organization_id} does not belong to plan {plan.identifier}.')
            obj = ActionResponsibleParty(
                action=action,
                organization=org,
                role=party.role,
                order=i,
            )
            obj.full_clean()
            obj.save()

    def _set_action_links(self, _info: gql.Info, action: Action, links: list[ActionLinkInput]) -> None:
        links_objs: list[ActionLink] = []
        ActionLink.objects.filter(action=action).delete()
        for i, link in enumerate(links):
            obj = ActionLink(action=action, url=link.url, title=link.title, order=i)
            obj.full_clean()
            links_objs.append(obj)
        ActionLink.objects.bulk_create(links_objs)

    def _create_action_m2m(self, info: gql.Info, action: Action, input: ActionInput) -> None:
        # Assign categories
        if input.category_ids is not sb.UNSET and input.category_ids is not None:
            self._set_action_categories(info, action, input.category_ids)

        # Assign choice attributes
        if input.attribute_values is not sb.UNSET and input.attribute_values is not None:
            self._set_action_attributes(info, action, input.attribute_values)

        if input.responsible_parties is not sb.UNSET and input.responsible_parties is not None:
            self._set_action_responsible_parties(info, action, input.responsible_parties)

        if input.links is not sb.UNSET and input.links is not None:
            self._set_action_links(info, action, input.links)

    @gql.mutation(permission_classes=[SuperuserOnly])
    def create_action(self, info: gql.Info, input: ActionInput) -> ActionNode:
        from actions.models import Action
        from orgs.models import Organization

        # Get the plan
        plan = gql.get_plan_or_error(info, input.plan_id)
        # FIXME: Check permissions after Action gets a PermissionPolicy

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

        action.clean()
        action.full_clean()
        action.save()

        self._create_action_m2m(info, action, input)

        action = Action.objects.get(pk=action.pk)
        return cast('ActionNode', action)  # pyright: ignore[reportInvalidCast]

    def _update_action(self, info: gql.Info, action: Action, input: ActionUpdateInput) -> bool:
        updated = False
        if input.name is not sb.UNSET:
            action.name = input.name
            updated = True
        if input.identifier is not sb.UNSET:
            if not action.plan.features.has_action_identifiers:
                raise ValidationError('Action identifiers are not enabled for this plan.')
            action.identifier = input.identifier
            updated = True
        if input.description is not sb.UNSET:
            action.description = input.description
            updated = True
        if input.lead_paragraph is not sb.UNSET:
            action.lead_paragraph = input.lead_paragraph
            updated = True
        if input.primary_org_id is not sb.UNSET:
            if input.primary_org_id is None:
                action.primary_org = None
            else:
                action.primary_org = get_or_error(info, Organization, pk=input.primary_org_id)
            updated = True

        # Update m2m
        if input.category_ids is not sb.UNSET and input.category_ids is not None:
            self._set_action_categories(info, action, input.category_ids)
            updated = True
        if input.attribute_values is not sb.UNSET and input.attribute_values is not None:
            self._set_action_attributes(info, action, input.attribute_values)
            updated = True
        if input.responsible_parties is not sb.UNSET and input.responsible_parties is not None:
            self._set_action_responsible_parties(info, action, input.responsible_parties)
            updated = True
        if input.links is not sb.UNSET and input.links is not None:
            self._set_action_links(info, action, input.links)
            updated = True

        if updated:
            action.full_clean()
            action.save()

        return updated

    @gql.mutation(
        permission_classes=[SuperuserOnly],
        description='Bulk update multiple actions. Returns the count and IDs of updated actions.',
    )
    def update_actions(self, info: gql.Info, plan_id: sb.ID, actions: list[ActionUpdateInput]) -> BulkUpdateActionsResult:
        plan = gql.get_plan_or_error(info, plan_id)

        plan_actions_by_id = {str(action.id): action for action in plan.actions.all()}
        plan_actions_by_identifier = {action.identifier: action for action in plan.actions.all()}

        updated_ids: list[sb.ID] = []
        for update in actions:
            action_ref = str(update.id)
            action = plan_actions_by_id.get(action_ref) or plan_actions_by_identifier.get(action_ref)
            if action is None:
                raise NotFoundError(info, f'Action with ID {action_ref} not found.')

            updated = self._update_action(info, action, update)
            if not updated:
                continue
            updated_ids.append(sb.ID(str(action.pk)))

        return BulkUpdateActionsResult(count=len(updated_ids), ids=updated_ids)

    @gql.mutation(
        permission_classes=[SuperuserOnly],
        description='Update one action. Returns the action.',
        graphql_type=ActionNode,
    )
    def update_action(self, info: gql.Info, plan_id: sb.ID, input: ActionUpdateInput) -> Action:
        plan = gql.get_plan_or_error(info, plan_id)
        action = plan.actions.get_queryset().by_id_or_identifier(input.id).first()
        if action is None:
            raise NotFoundError(info, f'Action with ID {input.id} not found.')
        _ = self._update_action(info, action, input)
        action.refresh_from_db()
        return action
