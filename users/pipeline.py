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


def update_user(backend, details, user, *args, **kwargs):
    if user is None:
        return

    changed = False
    for field in ('first_name', 'last_name', 'email'):
        val = getattr(user, field)
        if field in ('first_name', 'last_name') and val is None:
            val = ''
        if val != details[field]:
            setattr(user, field, val)
            changed = True
    if changed:
        user.save()
