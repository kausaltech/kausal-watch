from .models import User


def find_user_by_email(backend, details, user=None, social=None, *args, **kwargs):
    if user is not None:
        return

    details['email'] = details['email'].lower()
    try:
        user = User.objects.get(email=details['email'])
    except User.DoesNotExist:
        return

    if user.social_auth.exists():
        return

    return {
        'user': user,
        'is_new': False,
    }


def create_or_update_user(backend, details, user, *args, **kwargs):
    if user is None:
        uuid = details.get('uuid') or kwargs.get('uid')
        user = User(uuid=uuid)

    changed = False
    for field in ('first_name', 'last_name', 'email'):
        old_val = getattr(user, field)
        new_val = details.get(field)
        if field in ('first_name', 'last_name'):
            if old_val is None:
                old_val = ''
            if new_val is None:
                new_val = ''

        if new_val != old_val:
            setattr(user, field, new_val)
            changed = True

    if user.has_usable_password():
        user.set_unusable_password()
        changed = True

    if changed:
        user.save()

    return {
        'user': user,
    }
