from __future__ import annotations

import os
import re
import io
import hashlib
import typing
import uuid
import requests
import reversion
import logging

from datetime import timedelta

from django.db import models
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q

from easy_thumbnails.files import get_thumbnailer  # type: ignore
from image_cropping import ImageRatioField  # type: ignore
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from sentry_sdk import capture_exception
from wagtail.search import index
from wagtail.images.rect import Rect
from wagtail.admin.templatetags.wagtailadmin_tags import avatar_url as wagtail_avatar_url
import willow
from aplans.types import UserOrAnon, WatchRequest

from actions.models import ActionContactPerson
from orgs.models import Organization

from admin_site.models import Client
if typing.TYPE_CHECKING:
    from users.models import User as UserModel
    from django.db.models.manager import RelatedManager
    from actions.models import Action, Plan
    from indicators.models import Indicator
    from orgs.models import OrganizationPlanAdmin


logger = logging.getLogger(__name__)
User: typing.Type[UserModel] = get_user_model()  # type: ignore

DEFAULT_AVATAR_SIZE = 360


def determine_image_dim(image_width, image_height, width, height):
    for name in ('width', 'height'):
        x = locals()[name]
        if x is None:
            continue
        try:
            x = int(x)
            if x <= 0:
                raise ValueError()
            if x > 4000:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("invalid %s dimension: %s" % (name, x))

    if width is not None:
        width = int(width)
    if height is not None:
        height = int(height)

    ratio = image_width / image_height
    if not height:
        height = width / ratio
    elif not width:
        width = height * ratio

    return (width, height)


def image_upload_path(instance, filename):
    file_extension = os.path.splitext(filename)[1]
    return 'images/%s/%s%s' % (instance._meta.model_name, instance.id, file_extension)


class PersonQuerySet(models.QuerySet['Person']):
    def available_for_plan(self, plan: Plan, include_contact_persons=False):
        """Return persons from an organization related to the plan."""
        related = Organization.objects.filter(id=plan.organization_id) | plan.related_organizations.all()
        q = Q(pk__in=[])  # always false; Q() doesn't cut it; https://stackoverflow.com/a/39001190/14595546
        for org in related:
            q |= Q(organization__path__startswith=org.path)
        if include_contact_persons:
            q |= Q(id__in=ActionContactPerson.objects.filter(action__plan=plan).values_list('person'))
        return self.filter(q)

    def is_action_contact_person(self, plan):
        return self.filter(contact_for_actions__plan=plan).distinct()

    def visible_for_user(self, user: UserModel | None, plan: Plan):
        if not plan.features.public_contact_persons:
            if user is None or not user.is_authenticated or not user.can_access_admin(plan):
                return self.none()
        return self


@reversion.register()
class Person(index.Indexed, ClusterableModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    first_name = models.CharField(max_length=100, verbose_name=_('first name'))
    last_name = models.CharField(max_length=100, verbose_name=_('last name'))
    email = models.EmailField(verbose_name=_('email address'))
    title = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=pgettext_lazy("person's role", 'title')
    )
    postal_address = models.TextField(max_length=100, verbose_name=_('postal address'), null=True, blank=True)
    organization = models.ForeignKey(
        Organization, related_name='people', on_delete=models.PROTECT, verbose_name=_('organization'),
        help_text=_("What is this person's organization"),
    )
    user = models.OneToOneField(
        User, null=True, blank=True, related_name='person', on_delete=models.SET_NULL,
        editable=False, verbose_name=_('user'),
        help_text=_('Set if the person has an user account')
    )

    participated_in_training = models.BooleanField(
        null=True, default=False, verbose_name=_('participated in training'),
        help_text=_('Set to keep track who have attended training sessions')
    )

    image = models.ImageField(
        blank=True, upload_to=image_upload_path, verbose_name=_('image'),
        height_field='image_height', width_field='image_width'
    )
    image_cropping = ImageRatioField('image', '1280x720', verbose_name=_('image cropping'))  # pyright: ignore
    image_height = models.PositiveIntegerField(null=True, editable=False)
    image_width = models.PositiveIntegerField(null=True, editable=False)
    avatar_updated_at = models.DateTimeField(null=True, editable=False)

    contact_for_actions_unordered = models.ManyToManyField(
        'actions.Action',
        through='actions.ActionContactPerson',
        blank=True,
        verbose_name=_('contact for actions')
    )
    created_by = models.ForeignKey(
        User, related_name='created_persons', blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('created by'),
    )
    i18n = TranslationField(fields=('title',), default_language_field='organization__primary_language_lowercase')

    objects = PersonQuerySet.as_manager()

    search_fields = [
        index.FilterField('id'),
        index.AutocompleteField('first_name', partial_match=True),
        index.AutocompleteField('last_name', partial_match=True),
        index.AutocompleteField('title', partial_match=True),
        index.RelatedFields('organization', [
            index.AutocompleteField('distinct_name', partial_match=True),
            index.AutocompleteField('abbreviation', partial_match=True),
        ]),
    ]

    public_fields = [
        'id', 'uuid', 'first_name', 'last_name', 'email', 'title', 'organization', 'participated_in_training',
    ]

    # Type annotations for related models etc.
    contact_for_actions: RelatedManager[Action]
    contact_for_indicators: RelatedManager[Indicator]
    organization_plan_admins: RelatedManager[OrganizationPlanAdmin]
    general_admin_plans: RelatedManager[Plan]
    organization_id: int
    created_by_id: int

    class Meta:
        verbose_name = _('person')
        verbose_name_plural = _('people')
        ordering = ('last_name', 'first_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIXME: This is hacky
        field: ImageRatioField = self._meta.get_field('image_cropping')  # type: ignore
        field.width = DEFAULT_AVATAR_SIZE
        field.height = DEFAULT_AVATAR_SIZE

    def validate_unique(self, exclude=None):
        super().validate_unique(exclude)
        qs = Person.objects.all()
        if self.email:
            qs = qs.filter(email__iexact=self.email)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({
                'email': _('Person with this email already exists')
            })

    def set_avatar(self, photo):
        update_fields = ['avatar_updated_at']
        try:
            if not self.image or self.image.read() != photo:
                self.image.save('avatar.jpg', io.BytesIO(photo))  # type: ignore
                update_fields += ['image', 'image_height', 'image_width', 'image_cropping']
        except ValueError:
            pass
        self.avatar_updated_at = timezone.now()
        self.save(update_fields=update_fields)

    def download_avatar(self):
        url = None
        if self.email.endswith('@hel.fi'):
            url = f'https://api.hel.fi/avatar/{self.email}?s={DEFAULT_AVATAR_SIZE}&d=404'
        else:
            md5_hash = hashlib.md5(self.email.encode('utf8')).hexdigest()
            url = f'https://www.gravatar.com/avatar/{md5_hash}?f=y&s={DEFAULT_AVATAR_SIZE}&d=404'

        try:
            resp = requests.get(url, timeout=5)
        except requests.exceptions.RequestException as err:
            logger.exception('Connection error downloading avatar for %s' % str(self), exc_info=err)
            capture_exception(err)
            return

        # If it's a 404, we accept it as it is and try again sometime
        # later.
        if resp.status_code == 404:
            self.avatar_updated_at = timezone.now()
            self.save(update_fields=['avatar_updated_at'])
            return

        # If it's another error, it might be transient, so we want to try
        # again soon.
        try:
            resp.raise_for_status()
        except Exception as err:
            logger.exception('HTTP error downloading avatar for %s' % str(self), exc_info=err)
            capture_exception(err)
            return

        self.set_avatar(resp.content)

    def should_update_avatar(self):
        if not self.avatar_updated_at:
            return True
        return (timezone.now() - self.avatar_updated_at) > timedelta(minutes=60)

    def update_focal_point(self):
        if not self.image:
            return
        with self.image.open() as f:
            image = willow.Image.open(f)
            faces = image.detect_faces()

        if not faces:
            logger.warning('No faces detected for %s' % self)
            return

        left = min(face[0] for face in faces)
        top = min(face[1] for face in faces)
        right = max(face[2] for face in faces)
        bottom = max(face[3] for face in faces)
        self.image_cropping = ','.join([str(x) for x in (left, top, right, bottom)])

    def get_avatar_url(self, request: WatchRequest, size: str | None = None) -> str | None:
        if not self.image:
            return None

        try:
            with self.image.open() as file:  # noqa
                pass
        except FileNotFoundError:
            logger.info('Avatar file for %s not found' % self)
            return None

        if size is None:
            url = self.image.url
        else:
            m = re.match(r'(\d+)?(x(\d+))?', size)
            if not m:
                raise ValueError('Invalid size argument (should be "<width>x<height>")')
            width, _, height = m.groups()

            dim = determine_image_dim(self.image_width, self.image_height, width, height)

            tn_args: dict = {
                'size': dim,
            }
            if self.image_cropping:
                tn_args['focal_point'] = Rect(*[int(x) for x in self.image_cropping.split(',')])
                tn_args['crop'] = 30

            out_image = get_thumbnailer(self.image).get_thumbnail(tn_args)
            if out_image is None:
                return None
            url = out_image.url

        if request:
            url = request.build_absolute_uri(url)
        return url

    def save(self, *args, **kwargs):
        old_cropping = self.image_cropping
        ret = super().save(*args, **kwargs)
        if self.image and not old_cropping:
            self.update_focal_point()
            if self.image_cropping != old_cropping:
                super().save(update_fields=['image_cropping'])
        user = self.create_corresponding_user()
        if self.user != user:
            if self.user:
                # Deactivate `self.user` as we'll replace it with `user`
                # FIXME: We don't have access to any user to set as the deactivating user. There might not be a
                # deactivating user at all because we're not in a view. Setting `User.deactivated_by` to None may cause
                # problems.
                deactivating_user = None
                self.user.deactivate(deactivating_user)
            self.user = user
            super().save(update_fields=['user'])

        return ret

    def get_client_for_email_domain(self):
        # Handling of subdomains: We try to find a match for 'a.b.c' first, then for 'b.c', then for 'c'.
        email_domain = self.email.split('@')[1].lower()
        labels = email_domain.split('.')
        while labels:
            domain = '.'.join(labels)
            labels.pop(0)
            clients = Client.objects.filter(email_domains__domain=domain)
            if len(clients) == 1:
                return clients[0]
        return None

    def get_admin_client(self) -> Client | None:
        user = self.get_corresponding_user()

        plans = None
        if user is not None:
            # FIXME: Determine based on social_auth of last login
            plans = user.get_adminable_plans()
        else:
            plans = set()
            plans.update(list(self.contact_for_actions.all().values_list('plan', flat=True).distinct()))
            indicators = self.contact_for_indicators.all()
            for ind in indicators:
                plans.update(ind.plans.all())

        client = None
        if plans:
            clients = Client.objects.filter(plans__plan__in=plans).distinct()
            if len(clients) == 1:
                client = clients[0]
            else:
                logger.warning('Invalid number of clients found for %s [Person-%d]: %d' % (
                    self.email, self.id, len(clients)  # pyright: ignore
                ))
        if not client:
            client = self.get_client_for_email_domain()
        return client

    def get_notification_context(self):
        client = self.get_admin_client()
        assert client is not None
        context = {
            'person': {
                'first_name': self.first_name,
                'last_name': self.last_name,
            },
            'admin_url': client.get_admin_url(),
        }
        logo_context = client.get_notification_logo_context()
        if logo_context:
            context['logo'] = logo_context
        return context

    def get_corresponding_user(self):
        if self.user:
            return self.user

        return User.objects.filter(email__iexact=self.email).first()

    def create_corresponding_user(self):
        user = self.get_corresponding_user()
        email = self.email.lower()
        if user:
            created = False
            email_changed = user.email.lower() != email
            if email_changed:
                # If we change the email address to that of an existing deactivated user, we need to deactivate the
                # user with the old email address (done after this returns because it returns a user different from
                # `self.user`) and re-activate the user with the new email address (done further down in this method).
                try:
                    user = User.objects.get(email__iexact=email, is_active=False)
                except User.DoesNotExist:
                    pass
        else:
            user = User(
                email=email,
                uuid=uuid.uuid4(),
            )
            created = True
            email_changed = False

        if not created and not user.is_active:
            # Probably the user has been deactivated because the person has been deleted. Reactivate it.
            user.is_active = True
            reactivated = True
        else:
            reactivated = False

        set_password = created or reactivated or email_changed
        if set_password:
            client = self.get_client_for_email_domain()
            if client is not None and client.auth_backend:
                user.set_unusable_password()
            else:
                user.set_password(str(uuid.uuid4()))

        user.first_name = self.first_name
        user.last_name = self.last_name
        user.email = email
        user.save()
        return user

    def delete_and_deactivate_corresponding_user(self, acting_admin_user):
        target_user = getattr(self, 'user', None)
        if target_user:
            target_user.deactivate(acting_admin_user)
        self.delete()

    def visible_for_user(self, user: UserOrAnon, plan: Plan) -> bool:
        if not plan.features.public_contact_persons:
            if user is None or not user.is_authenticated or not user.can_access_admin(plan):
                return False
        return True

    def is_public_site_viewer(self, plan: Plan | None = None) -> bool:
        if plan is None:
            return self.plans_with_public_site_access.exists()
        return plan.pk in self.plans_with_public_site_access.values_list('plan_id', flat=True)

    def __str__(self):
        return "%s %s" % (self.first_name, self.last_name)


# Override wagtail default avatar_url templatetag (registered in people/apps.py)
def avatar_url(context, user: UserModel, size=50, gravatar_only=False):
    if user is None:
        return wagtail_avatar_url(user, size, gravatar_only)

    person = user.get_corresponding_person()
    if person is not None:
        url = person.get_avatar_url(request=context.get('request'), size='%dx%d' % (size, size))
        if url:
            return url
    return wagtail_avatar_url(user, size, gravatar_only)
