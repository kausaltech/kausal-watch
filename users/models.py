from helusers.models import AbstractUser


class User(AbstractUser):
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

    def can_modify_action(user, action=None):
        if user.is_superuser:
            return True
        if user.has_perm('actions.admin_action'):
            return True
        return user.is_contact_person_for_action(action)
