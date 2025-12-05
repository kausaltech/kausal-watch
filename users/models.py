from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Literal, overload

from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from wagtail.users.models import UserProfile

from orgs.models import Organization, OrganizationMetadataAdmin
from users.managers import UserManager

from .base import AbstractUser

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from rest_framework.authtoken.models import Token

    from kausal_common.models.types import FK, RevOne

    from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

    from actions.models import Action, ActionContactPerson, ActionResponsibleParty, ModelWithRole, Plan
    from actions.models.action import ActionQuerySet
    from actions.models.plan import PlanQuerySet
    from indicators.models import Indicator, IndicatorQuerySet
    from people.models import Person


class ModerationAction(StrEnum):
    PUBLISH = auto()
    APPROVE = auto()


@dataclass
class UserPermissionCache:
    user: User

    @cached_property
    def corresponding_person(self) -> Person | None:
        from people.models import Person

        try:
            person = self.user.person
        except Person.DoesNotExist:
            person = None

        if person is None:
            person = Person.objects.filter(email__iexact=self.user.email).first()
        return person

    @cached_property
    def active_admin_plan(self) -> Plan:
        return self.user.get_active_admin_plan()

    @cached_property
    def contact_for_actions_by_role(self) -> dict[ActionContactPerson.Role, set[int]]:
        from actions.models import ActionContactPerson

        if not self.corresponding_person:
            return {}
        acps = ActionContactPerson.objects.filter(person=self.corresponding_person)
        by_role: dict[ActionContactPerson.Role, set[int]] = {role: set() for role in ActionContactPerson.Role}
        for acp in acps:
            role = ActionContactPerson.Role(acp.role)
            by_role[role].add(acp.action_id)
        return by_role

    @cached_property
    def contact_for_actions(self) -> set[int]:
        person = self.corresponding_person
        if not person:
            return set()

        actions = set()
        for role_actions in self.contact_for_actions_by_role.values():
            actions.update(role_actions)
        return actions

    @cached_property
    def contact_for_indicators(self) -> set[int]:
        person = self.corresponding_person
        if not person:
            return set()
        return {ind.id for ind in person.contact_for_indicators.all()}

    @cached_property
    def admin_for_organizations(self) -> list[Organization]:
        person = self.corresponding_person
        if not person:
            return []
        opas = Organization.objects.filter(organization_plan_admins__person=person).distinct()
        return list(opas)

    @cached_property
    def admin_for_organization_ids(self) -> set[int]:
        return {org.id for org in self.admin_for_organizations}

    @cached_property
    def general_admin_for_plans(self) -> set[int]:
        from actions.models import Plan
        person = self.corresponding_person
        if not person:
            return set()
        return set(Plan.objects.filter(general_admins__person=self.corresponding_person).values_list('id', flat=True))


class UserRelatedModelsCache:
    _corresponding_person: Person | None
    _active_admin_plan: Plan
    _adminable_plans: PlanQuerySet
    _org_admin_for_actions: ActionQuerySet
    _org_admin_for_indicators: IndicatorQuerySet
    _contact_for_actions: set[int]
    _contact_for_indicators: set[int]
    _contact_for_actions_by_role: dict[ActionContactPerson.Role, set[int]]
    _contact_for_plan_actions: dict[int, set[int]]
    _contact_for_plan_indicators: dict[int, set[int]]
    _general_admin_for_plans: set[int]


class User(AbstractUser):
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    email: models.EmailField[str, str] = models.EmailField(_('email address'), unique=True) # type: ignore[assignment]
    selected_admin_plan: FK[Plan | None] = models.ForeignKey(
        'actions.Plan', null=True, blank=True, on_delete=models.SET_NULL,
    )
    deactivated_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    deactivated_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
    )

    objects: ClassVar[UserManager] = UserManager()  # type: ignore[assignment]

    auth_token: Token
    person: Person
    wagtail_userprofile: RevOne[User, UserProfile]
    _corresponding_person: Person | None
    _active_admin_plan: Plan
    _adminable_plans: models.QuerySet[Plan]
    _instance_visibility_perms: set[InstancesVisibleForMixin.VisibleFor]
    _instance_editable_perms: set[InstancesEditableByMixin.EditableBy]
    _org_admin_for_actions: ActionQuerySet
    _org_admin_for_indicators: IndicatorQuerySet
    _contact_for_actions: set[int]
    _contact_for_actions_by_role: dict[ActionContactPerson.Role, set[int]]
    _general_admin_for_plans: set[int]


    autocomplete_search_field = 'email'

    def save(self: User, *args, **kwargs):
        result = super().save(*args, **kwargs)
        # Create Wagtail user profile in order to force the light color theme
        # FIXME: Remove this and fix dark mode support
        UserProfile.objects.get_or_create(
            user=self,
            defaults={
                'theme': UserProfile.AdminColorThemes.LIGHT,
                'preferred_language': 'en',
            }
        )
        return result

    def get_cache(self) -> UserRelatedModelsCache:
        if not hasattr(self, '_cache'):
            self._cache = UserRelatedModelsCache()
        return self._cache

    @cached_property
    def perms(self) -> UserPermissionCache:
        return UserPermissionCache(user=self)

    def autocomplete_label(self):
        return self.email

    def get_corresponding_person(self) -> Person | None:
        return self.perms.corresponding_person

    def is_contact_person_for_action(self, action: Action | None = None) -> bool:
        if action is None:
            return bool(self.perms.contact_for_actions)
        return action.pk in self.perms.contact_for_actions

    def has_contact_person_role_for_action(self, role: ActionContactPerson.Role, action: Action | None = None) -> bool:
        if action is None:
            return bool(self.perms.contact_for_actions_by_role.get(role, set()))
        return action.pk in self.perms.contact_for_actions_by_role[role]

    def is_contact_person_for_indicator(self, indicator: Indicator | None = None) -> bool:
        if indicator is None:
            return bool(self.perms.contact_for_indicators)
        return indicator.pk in self.perms.contact_for_indicators

    def is_contact_person_for_action_in_plan(self, plan: Plan, action: Action | None = None) -> bool:
        cache = self.get_cache()
        if not hasattr(cache, '_contact_for_plan_actions'):
            cache._contact_for_plan_actions = {}

        if plan.id in cache._contact_for_plan_actions:
            plan_actions = cache._contact_for_plan_actions[plan.id]
            if action is None:
                return bool(plan_actions)
            return action.id in plan_actions

        plan_actions = set()
        cache._contact_for_plan_actions[plan.id] = plan_actions
        person = self.get_corresponding_person()
        if not person:
            return False

        plan_actions.update({act.id for act in person.contact_for_actions.filter(plan=plan)})
        if action is None:
            return bool(plan_actions)
        return action.id in plan_actions

    def is_contact_person_for_indicator_in_plan(self, plan: Plan, indicator: Indicator | None = None) -> bool:
        cache = self.get_cache()
        if not hasattr(cache, '_contact_for_plan_indicators'):
            cache._contact_for_plan_indicators = {}

        if plan.id in cache._contact_for_plan_indicators:
            plan_indicators = cache._contact_for_plan_indicators[plan.id]
            if indicator is None:
                return bool(plan_indicators)
            return indicator.id in plan_indicators

        plan_indicators = set()
        cache._contact_for_plan_indicators[plan.id] = plan_indicators
        person = self.get_corresponding_person()
        if not person:
            return False

        plan_indicators.update({act.id for act in person.contact_for_indicators.filter(levels__plan=plan)})
        if indicator is None:
            return bool(plan_indicators)
        return indicator.id in plan_indicators

    def is_contact_person_in_plan(self, plan: Plan) -> bool:
        return self.is_contact_person_for_action_in_plan(plan) or self.is_contact_person_for_indicator_in_plan(plan)

    def is_general_admin_for_plan(self, plan: Plan | None = None):
        if self.is_superuser:
            return True

        # Cache the general admin status
        cache = self.get_cache()
        if hasattr(cache, '_general_admin_for_plans'):
            plans = cache._general_admin_for_plans
            if plan is None:
                return bool(plans)
            return plan.pk in plans

        plans = set[int]()
        cache._general_admin_for_plans = plans
        person = self.get_corresponding_person()
        if not person:
            return False

        plans.update({plan.id for plan in person.general_admin_plans.all()})
        if plan is None:
            return bool(plans)
        return plan.pk in plans

    def _get_editable_roles[Role: ModelWithRole.Role](
            self, action: Action, _class: type[ModelWithRole[Role]],
        ) -> Sequence[Role | None]:
        if self.is_general_admin_for_plan(action.plan):
            return _class.get_roles()
        person = self.get_corresponding_person()
        if person is None:
            return []
        return _class.get_roles_editable_in_action_by(action, person)

    def get_editable_contact_person_roles(self, action: Action) -> Sequence[ActionContactPerson.Role | None]:
        """Return a list of roles so that this user can edit contact persons with those roles for the given action."""
        from actions.models import ActionContactPerson
        roles = self._get_editable_roles(action, ActionContactPerson)
        return roles

    def get_editable_responsible_party_roles(self, action: Action) -> Iterable[ActionResponsibleParty.Role|None]:
        from actions.models import ActionResponsibleParty
        return self._get_editable_roles(action, ActionResponsibleParty)

    def _get_admin_orgs(self) -> models.QuerySet[Organization]:
        person = self.get_corresponding_person()
        if not person:
            return Organization.objects.none()

        orgs = person.organization_plan_admins.values_list('organization')
        return Organization.objects.filter(id__in=orgs)

    def is_organization_admin_for_action(self, action: Action | None = None, plan: Plan | None = None):
        cache = self.get_cache()
        if hasattr(cache, '_org_admin_for_actions'):
            actions = cache._org_admin_for_actions
        else:
            from actions.models import Action
            actions = Action.objects.get_queryset()
            if plan:
                actions = actions.filter(plan=plan)
            actions = actions.user_is_org_admin_for(self)
            cache._org_admin_for_actions = actions
        # Ensure below that the actions queryset is evaluated to make
        # the cache efficient (it will use queryset's cache)
        if action is None:
            return bool(actions)
        return action in actions

    def is_organization_admin_for_indicator(self, indicator: Indicator | None = None) -> bool:
        indicators = None
        cache = self.get_cache()
        if self.is_superuser:
            return True
        if hasattr(cache, '_org_admin_for_indicators'):
            indicators = cache._org_admin_for_indicators
        else:
            from indicators.models import Indicator
            indicators = Indicator.objects.qs.filter(organization__in=self.get_adminable_organizations()).distinct()
            cache._org_admin_for_indicators = indicators
        # Ensure below that the indicators queryset is evaluated to make
        # the cache efficient (it will use queryset's cache)
        if indicator is None:
            return bool(indicators)
        return indicator in indicators

    def get_adminable_organizations(self):
        if self.is_superuser:
            return Organization.objects.all()

        return self._get_admin_orgs()

    @overload
    def get_active_admin_plan(self, required: Literal[False]) -> Plan | None: ...

    @overload
    def get_active_admin_plan(self, required: Literal[True] = True) -> Plan: ...

    def get_active_admin_plan(self, required: bool = True) -> Plan | None:
        cache = self.get_cache()
        if hasattr(cache, '_active_admin_plan'):
            return cache._active_admin_plan

        plans = self.get_adminable_plans()
        if len(plans) == 0:
            if required:
                raise Exception("No active admin plan")
            return None
        if len(plans) == 1:
            cache._active_admin_plan = plans[0]
            return cache._active_admin_plan

        selected_plan = self.selected_admin_plan
        if selected_plan is not None:
            for plan in plans:
                if plan == selected_plan:
                    cache._active_admin_plan = plan
                    return plan

        # If the plan is not set in session, select the
        # lastly created one.
        plan = sorted(plans, key=lambda x: x.created_at, reverse=True)[0]

        self.selected_admin_plan = plan
        self.save(update_fields=['selected_admin_plan'])
        cache._active_admin_plan = plan
        return plan

    def get_adminable_plans(self) -> PlanQuerySet:
        from actions.models import Plan

        # Cache adminable plans for each request
        cache = self.get_cache()
        if hasattr(cache, '_adminable_plans'):
            return cache._adminable_plans

        is_action_contact = self.is_contact_person_for_action()
        is_indicator_contact = self.is_contact_person_for_indicator()
        is_general_admin = self.is_general_admin_for_plan()
        is_org_admin = self.is_organization_admin_for_action()
        is_indicator_org_admin = self.is_organization_admin_for_indicator()
        if not self.is_superuser and not is_action_contact and not is_general_admin \
                and not is_org_admin and not is_indicator_contact and not is_indicator_org_admin:
            cache._adminable_plans = Plan.objects.qs.none()
            return cache._adminable_plans

        if self.is_superuser:
            plans = Plan.objects.qs
        else:
            q = Q(actions__in=self.perms.contact_for_actions)
            q |= Q(indicators__in=self.perms.contact_for_indicators)
            q |= Q(id__in=cache._general_admin_for_plans)
            q |= Q(actions__in=cache._org_admin_for_actions)
            q |= Q(indicators__in=cache._org_admin_for_indicators)
            plans = Plan.objects.qs.filter(q).distinct()
        cache._adminable_plans = plans
        return plans

    def get_viewable_plans(self) -> models.QuerySet[Plan]:
        from actions.models import Plan
        return Plan.objects.filter(public_site_viewers__person=self.person)

    def can_access_admin(self, plan: Plan | None = None) -> bool:
        """Can the user access the admin interface in general or for a given plan."""

        if self.is_superuser:
            return True

        adminable_plans = {p.pk for p in self.get_adminable_plans()}
        if plan is None:
            if len(adminable_plans) == 0:
                return False
            return True
        return plan.pk in adminable_plans

    def can_access_public_site(self, plan: Plan | None = None) -> bool:
        """Can the user access the public site (authenticated) in general or for a given plan."""
        if self.can_access_admin(plan):
            return True
        return self.person.is_public_site_viewer(plan)

    def can_modify_action(self, action: Action | None = None, plan: Plan | None = None):
        if self.is_superuser:
            return True
        if plan is None:
            if action is None:
                plan = self.get_active_admin_plan()
            else:
                plan = action.plan

        # At this point, `plan` is guaranteed to not be None
        if self.is_general_admin_for_plan(plan):
            return True
        if action is not None and action.is_merged():
            # Merged actions can only be edited by admins
            return False
        return self.is_contact_person_for_action_in_plan(plan, action) \
            or self.is_organization_admin_for_action(action, plan)

    def can_create_action(self, plan: Plan):
        assert plan is not None
        if plan.actions_locked:
            return False
        if self.is_superuser:
            return True
        return self.is_general_admin_for_plan(plan)

    def can_delete_action(self, plan: Plan, action: Action | None = None):
        return self.can_create_action(plan)

    def _check_moderation_publish_permissions(self, action: Action, person: Person) -> bool:
        if action.plan.features.moderation_workflow is None:
            return False
        if action.plan.features.moderation_workflow.tasks.count() > 1:
            # If the acceptance chain is longer, moderators are restricted to only the first acceptance task
            # (and are not allowed to publish)
            return False
        return self._check_moderation_approve_permissions(action, person)

    def _check_moderation_approve_permissions(self, action: Action, person: Person) -> bool:
        from actions.models.action import ActionContactPerson
        return action.contact_persons.filter(role=ActionContactPerson.Role.MODERATOR, person=person).exists()

    def _check_moderation_permissions(self, moderation_action: ModerationAction, action: Action) -> bool:
        # Only called currently if a plan has a moderation workflow enabled
        if self.is_superuser:
            return True
        person = self.get_corresponding_person()
        if not person:
            return False
        if self.is_general_admin_for_plan(action.plan):
            return True
        # TODO: Cache?
        if moderation_action == ModerationAction.PUBLISH:
            return self._check_moderation_publish_permissions(action, person)
        if moderation_action == ModerationAction.APPROVE:
            return self._check_moderation_approve_permissions(action, person)
        return None

    def can_publish_action(self, action: Action):
        return self._check_moderation_permissions(ModerationAction.PUBLISH, action)

    def can_approve_action(self, action: Action):
        return self._check_moderation_permissions(ModerationAction.APPROVE, action)

    def can_create_indicator(self, plan):
        if self.is_superuser:
            return True
        return self.is_general_admin_for_plan(plan)

    def can_modify_indicator(self, indicator=None):
        if self.is_superuser:
            return True
        if indicator is None:
            plans = [self.get_active_admin_plan()]
        else:
            plans = list(indicator.plans.all())

        if plans is not None:
            for plan in plans:
                if self.is_general_admin_for_plan(plan):
                    return True

        return self.is_contact_person_for_indicator(indicator) or self.is_organization_admin_for_indicator(indicator)

    def can_modify_category(self, category=None):
        if self.is_superuser:
            return True
        if category is None:
            plan = self.get_active_admin_plan()
        else:
            plan = category.type.plan
        return self.is_general_admin_for_plan(plan)

    def can_create_category(self, category_type):
        if self.is_superuser:
            return True
        return self.is_general_admin_for_plan(category_type.plan)

    def can_delete_category(self, category_type):
        if self.is_superuser:
            return True
        return self.is_general_admin_for_plan(category_type.plan)

    def can_modify_organization(self, organization=None):
        # TBD: How does this method differ from Organization.user_can_edit()? Does it make sense to have both?
        if self.is_superuser:
            return True
        person = self.get_corresponding_person()
        if not person:
            return False
        if organization is None:
            # FIXME: Make sure we don't allow plan admins to modify organizations unrelated to them
            return OrganizationMetadataAdmin.objects.filter(person=person).exists()
        # For now we ignore OrganizationMetadataAdmin and let plan admins modify organizations
        # return organization.organization_metadata_admins.filter(person=person).exists()
        return organization.user_can_edit(self)

    def can_create_organization(self):
        if self.is_superuser:
            return True
        return self.is_general_admin_for_plan()

    def can_delete_organization(self):
        if self.is_superuser:
            return True
        # FIXME: Make sure we don't allow plan admins to delete organizations unrelated to them
        return self.is_general_admin_for_plan()

    def can_modify_person(self, person: Person | None = None) -> bool:
        if self.is_superuser:
            return True
        self_person = self.get_corresponding_person()
        if not self_person:
            return False
        # FIXME: Probably crap
        return self.can_modify_organization(self_person.organization)

    def can_create_person(self):
        # FIXME: Probably crap
        return self.can_modify_person()

    def can_delete_person(self):
        # FIXME: Probably crap
        return self.can_modify_person()

    def can_deactivate_user(self, user):
        if self.is_superuser:
            return True
        plan = self.get_active_admin_plan()
        if not self.is_general_admin_for_plan(plan):
            return False
        if user.get_adminable_plans().count() == 0:
            return False
        for user_plan in user.get_adminable_plans():
            if not self.is_general_admin_for_plan(user_plan):
                raise PermissionDenied(
                    _('No permission to remove the user belonging to plans you are not managing.'),
                )
        return True

    def can_edit_or_delete_person_within_plan(
        self, person: Person, plan: Plan | None = None, orgs: dict | None = None,
    ) -> bool:
        # orgs is a performance optimization, a pre-populated
        # dict for cases where this function is called from within a loop

        if self.is_superuser:
            return True

        # The creating user has edit rights until the created user first logs in
        if person.created_by_id == self.id and person.user and not person.user.last_login:  # pyright: ignore
            return True

        if plan is not None and self.is_general_admin_for_plan(plan):
            if orgs is not None:
                return person.organization_id in orgs
            return person.organization_id in Organization.objects.qs.available_for_plan(plan).values_list('id', flat=True)
        return False

    def deactivate(self, admin_user):
        self.is_active = False
        self.deactivated_by = admin_user
        self.deactivated_at = timezone.now()
        self.save()

    def __getstate__(self) -> dict[str, Any]:
        statedict = super().__getstate__()
        # Do not pickle data that is only used for caching
        if '_cache' in statedict:
            del statedict['_cache']
        return statedict
