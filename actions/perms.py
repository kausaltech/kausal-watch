from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from .models import Action, ActionResponsibleParty, ActionTask, Plan, \
    ActionSchedule, ActionStatus, Category, CategoryType
from django_orghierarchy.models import Organization
from indicators.models import ActionIndicator, Indicator, \
    RelatedIndicator, Unit, IndicatorLevel
from django.contrib.auth import get_user_model
from people.models import Person


User = get_user_model()


ACTIONS_APP = 'actions'

ALL_PERMS = ('view', 'change', 'delete', 'add')


def _get_perm_objs(model, perms):
    content_type = ContentType.objects.get_for_model(model)
    perms = ['%s_%s' % (x, model._meta.model_name) for x in perms]
    perm_objs = Permission.objects.filter(content_type=content_type, codename__in=perms)
    return list(perm_objs)


def add_model_perms(model, user, perms):
    user.user_permissions.add(*_get_perm_objs(model, perms))


def remove_model_perms(model, user, perms):
    user.user_permissions.remove(*_get_perm_objs(model, perms))


def add_contact_person_perms(user):
    # Add general permissions
    add_model_perms(Action, user, ('view', 'change'))
    add_model_perms(ActionTask, user, ('view', 'change', 'delete', 'add'))
    add_model_perms(Person, user, ('view', 'change', 'add'))
    for model in (ActionResponsibleParty, ActionIndicator, Indicator, RelatedIndicator, Unit):
        add_model_perms(model, user, ALL_PERMS)
    add_model_perms(Organization, user, ('view',))
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=['is_staff'])


PLAN_ADMIN_PERMS = (
    (Action, ('admin',)),
    (Plan, ('view', 'change')),
    (ActionStatus, ALL_PERMS),
    (ActionSchedule, ALL_PERMS),
    (CategoryType, ALL_PERMS),
    (Category, ALL_PERMS),
    (IndicatorLevel, ALL_PERMS),
    (User, ('view',))
)


def add_plan_admin_perms(user):
    add_contact_person_perms(user)
    for model, perms in PLAN_ADMIN_PERMS:
        add_model_perms(model, user, perms)


def remove_plan_admin_perms(user):
    # Contact person perms are not removed, because they are being
    # dynamically checked for specific objects anyway.
    for model, perms in PLAN_ADMIN_PERMS:
        remove_model_perms(model, user, perms)


class ActionRelatedAdminPermMixin:
    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        return request.user.can_modify_action(obj)

    def has_add_permission(self, request, obj=None):
        if not super().has_add_permission(request, obj):
            return False
        return request.user.can_modify_action(obj)

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        return request.user.can_modify_action(obj)
