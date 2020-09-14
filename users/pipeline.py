import logging

from social_core.backends.oauth import OAuthAuth

from .models import User

logger = logging.getLogger('users.login')


def log_login_attempt(backend, details, *args, **kwargs):
    response = kwargs.get('response', {})
    request = kwargs['request']

    host = request.get_host()
    id_parts = ['backend=%s' % backend.name, 'host=%s' % host]
    email = response.get('email')
    if email:
        id_parts.append('email=%s' % email)
    tid = response.get('tid')
    if tid:
        id_parts.append('tid=%s' % tid)

    oid = response.get('oid')
    if oid:
        id_parts.append('oid=%s' % oid)
    else:
        sub = response.get('sub')
        if sub:
            id_parts.append('sub=%s' % sub)

    logger.info('Login attempt (%s)' % ', '.join(id_parts))

    if isinstance(backend, OAuthAuth):
        try:
            backend.validate_state()
        except Exception as e:
            logger.warning('Login failed with invalid state: %s' % str(e))


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
        msg = 'Created new user'
    else:
        msg = 'Existing user found'
        uuid = user.uuid
    logger.info('%s (uuid=%s, email=%s)' % (msg, uuid, details.get('email')))

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
        logger.info('User saved (uuid=%s, email=%s)' % (uuid, details.get('email')))
        user.save()

    return {
        'user': user,
    }
