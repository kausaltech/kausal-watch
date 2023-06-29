from __future__ import annotations
import typing

from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from users.managers import UserManager
from orgs.models import Organization, OrganizationMetadataAdmin

from .base import AbstractUser

if typing.TYPE_CHECKING:
    from actions.models import Plan, Action
    from people.models import Person


class User(AbstractUser):
    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    email = models.EmailField(_('email address'), unique=True)
    selected_admin_plan = models.ForeignKey(
        'actions.Plan', null=True, blank=True, on_delete=models.SET_NULL
    )
    deactivated_at = models.DateTimeField(
        null=True,
        blank=True
    )
    deactivated_by = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True
    )

    _corresponding_person: Person

    autocomplete_search_field = 'email'

    def autocomplete_label(self):
        return self.email

    def get_corresponding_person(self) -> typing.Optional[Person]:
        if hasattr(self, '_corresponding_person'):
            return self._corresponding_person

        from people.models import Person

        try:
            person = self.person
        except Person.DoesNotExist:
            person = None

        if person is None:
            try:
                person = Person.objects.get(email__iexact=self.email)
            except Person.DoesNotExist:
                pass
        setattr(self, '_corresponding_person', person)
        return person

    def is_contact_person_for_action(self, action=None):
        # Cache the contact person status
        if hasattr(self, '_contact_for_actions'):
            actions = self._contact_for_actions
            if action is None:
                return bool(actions)
            return action.pk in actions

        actions = set()
        self._contact_for_actions = actions
        person = self.get_corresponding_person()
        if not person:
            return False

        actions.update({act.id for act in person.contact_for_actions.all()})
        if action is None:
            return bool(actions)
        else:
            return action.pk in actions

    def is_contact_person_for_indicator(self, indicator=None):
        if hasattr(self, '_contact_for_indicators'):
            indicators = self._contact_for_indicators
            if indicator is None:
                return bool(indicators)
            return indicator.pk in indicators

        indicators = set()
        self._contact_for_indicators = indicators
        person = self.get_corresponding_person()
        if not person:
            return False

        indicators.update({ind.id for ind in person.contact_for_indicators.all()})
        if indicator is None:
            return bool(indicators)
        else:
            return indicator.pk in indicators

    def is_contact_person_for_action_in_plan(self, plan, action=None):
        if not hasattr(self, '_contact_for_plan_actions'):
            self._contact_for_plan_actions = {}

        if plan.id in self._contact_for_plan_actions:
            plan_actions = self._contact_for_plan_actions[plan.id]
            if action is None:
                return bool(plan_actions)
            return action.id in plan_actions

        plan_actions = set()
        self._contact_for_plan_actions[plan.id] = plan_actions
        person = self.get_corresponding_person()
        if not person:
            return False

        plan_actions.update({act.id for act in person.contact_for_actions.filter(plan=plan)})
        if action is None:
            return bool(plan_actions)
        return action.id in plan_actions

    def is_contact_person_for_indicator_in_plan(self, plan, indicator=None):
        if not hasattr(self, '_contact_for_plan_indicators'):
            self._contact_for_plan_indicators = {}

        if plan.id in self._contact_for_plan_indicators:
            plan_indicators = self._contact_for_plan_indicators[plan.id]
            if indicator is None:
                return bool(plan_indicators)
            return indicator.id in plan_indicators

        plan_indicators = set()
        self._contact_for_plan_indicators[plan.id] = plan_indicators
        person = self.get_corresponding_person()
        if not person:
            return False

        plan_indicators.update({act.id for act in person.contact_for_indicators.filter(levels__plan=plan)})
        if indicator is None:
            return bool(plan_indicators)
        return indicator.id in plan_indicators

    def is_contact_person_in_plan(self, plan):
        return self.is_contact_person_for_action_in_plan(plan) or self.is_contact_person_for_indicator_in_plan(plan)

    def is_general_admin_for_plan(self, plan=None):
        if self.is_superuser:
            return True

        # Cache the general admin status
        if hasattr(self, '_general_admin_for_plans'):
            plans = self._general_admin_for_plans
            if plan is None:
                return bool(plans)
            return plan.pk in plans

        plans = set()
        self._general_admin_for_plans = plans
        person = self.get_corresponding_person()
        if not person:
            return False

        plans.update({plan.id for plan in person.general_admin_plans.all()})
        if plan is None:
            return bool(plans)
        else:
            return plan.pk in plans

    def _get_admin_orgs(self):
        person = self.get_corresponding_person()
        if not person:
            return Organization.objects.none()

        orgs = person.organization_plan_admins.values_list('organization')
        return Organization.objects.filter(id__in=orgs)

    def is_organization_admin_for_action(self, action=None):
        actions = None
        if hasattr(self, '_org_admin_for_actions'):
            actions = self._org_admin_for_actions
        else:
            Action = apps.get_model('actions', 'Action')
            actions = Action.objects.user_is_org_admin_for(self)
            self._org_admin_for_actions = actions
        # Ensure below that the actions queryset is evaluated to make
        # the cache efficient (it will use queryset's cache)
        if action is None:
            return bool(actions)
        return action in actions

    def is_organization_admin_for_indicator(self, indicator=None):
        indicators = None
        if hasattr(self, '_org_admin_for_indicators'):
            indicators = self._org_admin_for_indicators
        else:
            Indicator = apps.get_model('indicators', 'Indicator')
            indicators = Indicator.objects.filter(organization__in=self.get_adminable_organizations())
            self._org_admin_for_indicators = indicators
        # Ensure below that the indicators queryset is evaluated to make
        # the cache efficient (it will use queryset's cache)
        if indicator is None:
            return bool(indicators)
        return indicator in indicators

    def get_adminable_organizations(self):
        if self.is_superuser:
            return Organization.objects.all()

        return self._get_admin_orgs()

    def get_active_admin_plan(self, adminable_plans=None) -> Plan:
        if hasattr(self, '_active_admin_plan'):
            return self._active_admin_plan

        if adminable_plans is None:
            plans = self.get_adminable_plans()
        else:
            plans = adminable_plans
        if len(plans) == 0:
            return None
        if len(plans) == 1:
            self._active_admin_plan = plans[0]
            return self._active_admin_plan

        selected_plan = self.selected_admin_plan
        if selected_plan is not None:
            for plan in plans:
                if plan == selected_plan:
                    self._active_admin_plan = plan
                    return plan

        # If the plan is not set in session, select the
        # lastly created one.
        plan = sorted(plans, key=lambda x: x.created_at, reverse=True)[0]

        self.selected_admin_plan = plan
        self.save(update_fields=['selected_admin_plan'])
        self._active_admin_plan = plan
        return plan

    def get_adminable_plans(self) -> models.QuerySet[Plan]:
        from actions.models import Plan

        # Cache adminable plans for each request
        if hasattr(self, '_adminable_plans'):
            return self._adminable_plans

        is_action_contact = self.is_contact_person_for_action()
        is_indicator_contact = self.is_contact_person_for_indicator()
        is_general_admin = self.is_general_admin_for_plan()
        is_org_admin = self.is_organization_admin_for_action()
        is_indicator_org_admin = self.is_organization_admin_for_indicator()
        if not self.is_superuser and not is_action_contact and not is_general_admin \
                and not is_org_admin and not is_indicator_contact and not is_indicator_org_admin:
            self._adminable_plans = Plan.objects.none()
            return self._adminable_plans

        if self.is_superuser:
            plans = Plan.objects.all()
        else:
            q = Q(actions__in=self._contact_for_actions)
            q |= Q(indicators__in=self._contact_for_indicators)
            q |= Q(id__in=self._general_admin_for_plans)
            q |= Q(actions__in=self._org_admin_for_actions)
            q |= Q(indicators__in=self._org_admin_for_indicators)
            plans = Plan.objects.filter(q).distinct()
        self._adminable_plans = plans
        return plans

    def get_adminable_plans_mark_selected(self) -> models.QuerySet[Plan]:
        plans = self.get_adminable_plans()
        active_plan = self.get_active_admin_plan(plans)
        for plan in plans:
            if plan == active_plan:
                plan.is_active_admin = True
            else:
                plan.is_active_admin = False
        return plans

    def can_modify_action(self, action: Action = None, plan: Plan = None):
        if self.is_superuser:
            return True
        if plan is None:
            if action is None:
                plan = self.get_active_admin_plan()
            else:
                plan = action.plan

        if plan is not None:
            if self.is_general_admin_for_plan(plan):
                return True
        if action is not None and action.is_merged():
            # Merged actions can only be edited by admins
            return False
        return self.is_contact_person_for_action(action) \
            or self.is_organization_admin_for_action(action)

    def can_create_action(self, plan: Plan):
        assert plan is not None
        if plan.actions_locked:
            return False
        if self.is_superuser:
            return True
        return self.is_general_admin_for_plan(plan)

    def can_delete_action(self, plan: Plan, action: Action = None):
        return self.can_create_action(plan)

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
        else:
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

    def can_modify_person(self, person=None):
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
                    _('No permission to remove the user belonging to plans you are not managing.')
                )
        return True

    def deactivate(self, admin_user):
        if not admin_user.can_deactivate_user(self):
            raise PermissionDenied(_('You do not have permissions for removing users.'))
        self.is_active = False
        self.deactivated_by = admin_user
        self.deactivated_at = timezone.now()
        self.save()
