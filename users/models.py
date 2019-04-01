from django.db import models
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
        if not self.is_superuser and not is_contact and not is_general_admin:
            return []

        plans = set()
        if self.is_superuser:
            plans.update(Plan.objects.all())
        else:
            plans.update(Plan.objects.filter(actions__in=self._contact_for_actions).distinct())
            plans.update(Plan.objects.filter(id__in=self._general_admin_for_plans))

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
        return self.is_contact_person_for_action(action)
