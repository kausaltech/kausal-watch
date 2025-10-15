from __future__ import annotations

import hashlib
import io
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from django.conf import settings
from wagtail.users.models import UserProfile

from loguru import logger
from sentry_sdk import capture_exception
from social_core.backends.oauth import OAuthAuth

from kausal_common.auth.msgraph import get_user_photo_with_etag

from .base import uuid_to_username
from .models import User

if TYPE_CHECKING:
    from social_django import BaseAuth

logger = logger.bind(name='users.login')


def log_login_attempt(backend: BaseAuth, **kwargs):
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
    if settings.DEBUG and 'id_token' in response:
        logger.debug('ID token: %s' % response['id_token'])

    if isinstance(backend, OAuthAuth):
        try:
            backend.validate_state()
        except Exception as e:
            logger.warning('Login failed with invalid state: %s' % str(e))


def find_user_by_email(details: dict[str, Any], user: User | None = None, **_kwargs):
    if user is not None:
        return None

    details['email'] = details['email'].lower()
    try:
        user = User.objects.get(email=details['email'])
    except User.DoesNotExist:
        return None

    return {
        'user': user,
        'is_new': False,
    }


def create_or_update_user(details: dict[str, Any], user: User | None = None, **_kwargs):
    if user is None:
        uuid: str | UUID
        if 'uuid' in details:
            uuid = details['uuid']
        else:
            uuid = uuid4()
        user = User(uuid=uuid)
        msg = 'Created new user'
    else:
        msg = 'Existing user found'
        uuid = user.uuid
    log_ctx = {
        'user.uuid': uuid,
        'user.email': details.get('email'),
    }
    logger.info(msg, **log_ctx)

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
        logger.info('User saved', **log_ctx)
        user.save()

    return {
        'user': user,
    }


def update_avatar(backend: BaseAuth, details: dict[str, Any], user: User | None, *_args, **_kwargs):
    if backend.name != 'azure_ad' or user is None:
        return

    person = user.get_corresponding_person()

    log_ctx = {
        'user.uuid': user.uuid,
        'user.email': details.get('email'),
    }
    plogger = logger.bind(**log_ctx)

    plogger.info('Updating user photo')

    photo = None
    try:
        photo = get_user_photo_with_etag(user, old_etag=person.image_msgraph_etag if person else None)
    except Exception as e:
        plogger.exception('Failed to get user photo')
        capture_exception(e)

    if not photo:
        plogger.info('No photo found')
        return

    if photo.value is None:
        plogger.info('Photo unchanged; etag matched')
        return

    profile = UserProfile.get_for_user(user)

    photo_bytes = photo.value.content
    photo_hash = hashlib.md5(photo_bytes, usedforsecurity=False).hexdigest()
    if person:
        if person.image_hash == photo_hash:
            plogger.info('Photo unchanged; hashes match')
            person.image_msgraph_etag = photo.etag
            person.__class__.objects.filter(pk=person.pk).update(image_msgraph_etag=photo.etag)
            return
        try:
            person.set_avatar(photo_bytes, msgraph_etag=photo.etag)
        except Exception as e:
            plogger.exception('Failed to set avatar for person', **{'person.id': person.id})
            capture_exception(e)

    try:
        if not profile.avatar:
            profile.avatar.save('avatar.jpg', io.BytesIO(photo.value.content))
    except Exception as e:
        plogger.exception('Failed to set user profile photo')
        capture_exception(e)


def get_username(details: dict[str, Any], backend: BaseAuth, **kwargs):
    """
    Set the `username` argument.

    If the user exists already, use the existing username. Otherwise
    generate username from the `new_uuid` using the
    `uuid_to_username` function.
    """

    if backend.name != 'azure_ad':
        return None

    user = details.get('user')
    if not user:
        user_uuid = kwargs.get('uid')
        if not user_uuid:
            return None
        username = uuid_to_username(user_uuid)
    else:
        username = user.username

    return {
        'username': username,
    }
