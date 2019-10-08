from actions.perms import (
    add_contact_person_perms, remove_contact_person_perms,
    add_plan_admin_perms, remove_plan_admin_perms
)


def create_permissions(details, backend, response, user=None, *args, **kwargs):
    if user is None:
        return

    # If there is a person added for this user already in the system,
    # connect the models here.
    person = user.get_corresponding_person()
    if person and not person.user:
        person.user = user
        person.save(update_fields=['user'])

    if user.is_contact_person_for_action() or user.is_organization_admin_for_action():
        add_contact_person_perms(user)
    else:
        remove_contact_person_perms(user)

    if user.is_general_admin_for_plan():
        add_plan_admin_perms(user)
    else:
        remove_plan_admin_perms(user)
