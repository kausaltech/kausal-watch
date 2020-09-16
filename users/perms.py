import logging

from actions.models import Action
from actions.perms import (
    add_contact_person_perms, add_plan_admin_perms, remove_contact_person_perms, remove_plan_admin_perms
)
from indicators.models import Indicator

from .models import User

logger = logging.getLogger('users.perms')


def create_permissions(user, **kwargs):
    assert isinstance(user, User)

    # If there is a person added for this user already in the system,
    # connect the models here.
    person = user.get_corresponding_person()
    if person and not person.user:
        person.user = user
        person.save(update_fields=['user'])

    if person:
        logger.info('Found corresponding person: %s (uuid=%s, email=%s)' % (str(person), user.uuid, user.email))
    else:
        logger.info('No corresponding person found (uuid=%s, email=%s)' % (user.uuid, user.email))

    if user.is_contact_person_for_action() or user.is_organization_admin_for_action():
        add_contact_person_perms(user, Action)
        logger.info('Adding action contact person perms (uuid=%s, email=%s)' % (user.uuid, user.email))
    else:
        remove_contact_person_perms(user, Action)

    if user.is_contact_person_for_indicator():
        add_contact_person_perms(user, Indicator)
        logger.info('Adding indicator contact person perms (uuid=%s, email=%s)' % (user.uuid, user.email))
    else:
        remove_contact_person_perms(user, Indicator)

    if user.is_general_admin_for_plan():
        add_plan_admin_perms(user)
        logger.info('Adding general admin perms (uuid=%s, email=%s)' % (user.uuid, user.email))
    else:
        remove_plan_admin_perms(user)
