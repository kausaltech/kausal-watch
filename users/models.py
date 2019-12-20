from django.apps import apps
from django.db import models
from django.utils.translation import gettext_lazy as _
from helusers.models import AbstractUser


class User(AbstractUser):
    selected_admin_plan = models.ForeignKey(
        'actions.Plan', null=True, blank=True, on_delete=models.SET_NULL
    )

    def get_corresponding_person(self):
        from people.models import Person

        try:
            return Person.objects.get(email__iexact=self.email)
        except Person.DoesNotExist:
            return None

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
        plans.update({plan.id for plan in self.general_admin_plans.all()})
        if plan is None:
            return bool(plans)
        else:
            return plan.pk in plans

    def is_organization_admin_for_action(self, action=None):
        if hasattr(self, '_org_admin_for_actions'):
            actions = self._org_admin_for_actions
            if action is None:
                return bool(actions)
            return action.pk in actions

        actions = set()
        self._org_admin_for_actions = actions

        if not self.admin_orgs.exists():
            return

        orgs = self.get_adminable_organizations()

        Action = apps.get_model('actions', 'Action')
        rp_actions = Action.objects.filter(responsible_parties__organization__in=orgs).distinct()
        actions.update({act.id for act in rp_actions})

        if action is None:
            return bool(actions)
        else:
            return action.pk in actions

    def get_adminable_organizations(self):
        Organization = apps.get_model('django_orghierarchy', 'Organization')
        orgs = Organization.objects.filter(aplans_admin_users__user=self, dissolution_date=None)\
            .get_descendants(include_self=True).filter(dissolution_date=None).distinct()
        return orgs

    def get_active_admin_plan(self, adminable_plans=None):
        if adminable_plans is None:
            plans = self.get_adminable_plans()
        else:
            plans = adminable_plans
        if len(plans) == 0:
            return None
        if len(plans) == 1:
            return plans[0]

        selected_plan = self.selected_admin_plan
        if selected_plan is not None:
            for plan in plans:
                if plan == selected_plan:
                    return plan

        # If the plan is not set in session, select the
        # lastly created one.
        plan = sorted(plans, key=lambda x: x.created_at, reverse=True)[0]

        self.selected_admin_plan = plan
        self.save(update_fields=['selected_admin_plan'])
        return plan

    def get_adminable_plans(self):
        from actions.models import Plan

        is_contact = self.is_contact_person_for_action()
        is_general_admin = self.is_general_admin_for_plan()
        is_org_admin = self.is_organization_admin_for_action()
        if not self.is_superuser and not is_contact and not is_general_admin \
                and not is_org_admin:
            return []

        # Cache adminable plans for each request
        if hasattr(self, '_adminable_plans'):
            plans = self._adminable_plans
        else:
            plans = set()
            if self.is_superuser:
                plans.update(Plan.objects.all())
            else:
                plans.update(Plan.objects.filter(actions__in=self._contact_for_actions).distinct())
                plans.update(Plan.objects.filter(id__in=self._general_admin_for_plans))
                plans.update(Plan.objects.filter(actions__in=self._org_admin_for_actions).distinct())
            self._adminable_plans = plans

        plans = sorted(list(plans), key=lambda x: x.name)
        active_plan = self.get_active_admin_plan(plans)
        for plan in plans:
            if plan == active_plan:
                plan.is_active_admin = True
            else:
                plan.is_active_admin = False
        return plans

    def can_modify_action(self, action=None):
        if self.is_superuser:
            return True
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


class OrganizationAdmin(models.Model):
    user = models.ForeignKey(
        User, verbose_name=_('user'), on_delete=models.CASCADE,
        related_name='admin_orgs'
    )
    organization = models.ForeignKey(
        'django_orghierarchy.Organization', verbose_name=_('organization'),
        on_delete=models.CASCADE, related_name='aplans_admin_users'
    )

    class Meta:
        unique_together = (('user', 'organization'),)
        verbose_name = _('admin for organization')
        verbose_name_plural = _('admins for organization')

    def __str__(self):
        if self.user is not None and self.organization is not None:
            return '%s: %s' % (str(self.organization), str(self.user))
        return '[unknown]'
