import os
import re
import io
import hashlib
import uuid
import requests
import logging

from datetime import timedelta

from django.db import models
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q

from easy_thumbnails.files import get_thumbnailer
from image_cropping import ImageRatioField
from modelcluster.models import ClusterableModel
from sentry_sdk import capture_exception
from wagtail.search import index
from wagtail.images.rect import Rect
from wagtail.admin.templatetags.wagtailadmin_tags import avatar_url as wagtail_avatar_url
import willow

from orgs.models import Organization

from admin_site.models import Client


logger = logging.getLogger(__name__)
User = get_user_model()

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


class PersonQuerySet(models.QuerySet):
    def available_for_plan(self, plan):
        related = Organization.objects.filter(id=plan.organization_new_id) | plan.related_organizations_new.all()
        # TODO: include_self probably doesn't work anymore?
        all_related = related.get_descendants(include_self=True)
        q = Q(organization_new__in=all_related)
        return self.filter(q)

    def is_action_contact_person(self, plan):
        return self.filter(contact_for_actions__plan=plan).distinct()


class Person(index.Indexed, ClusterableModel):
    first_name = models.CharField(max_length=100, verbose_name=_('first name'))
    last_name = models.CharField(max_length=100, verbose_name=_('last name'))
    email = models.EmailField(verbose_name=_('email address'))
    title = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=pgettext_lazy("person's role", 'title')
    )
    postal_address = models.TextField(max_length=100, verbose_name=_('postal address'), null=True, blank=True)
    organization = models.ForeignKey(
        'django_orghierarchy.Organization', related_name='people',
        on_delete=models.PROTECT, verbose_name=_('organization'),
        help_text=_("What is this person's organization")
    )
    organization_new = models.ForeignKey(
        Organization, related_name='people', on_delete=models.PROTECT, verbose_name=_('organization'),
        help_text=_("What is this person's organization"),
        null=True,  # TODO: Remove after migrating the data
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
    image_cropping = ImageRatioField('image', '1280x720', verbose_name=_('image cropping'))
    image_height = models.PositiveIntegerField(null=True, editable=False)
    image_width = models.PositiveIntegerField(null=True, editable=False)
    avatar_updated_at = models.DateTimeField(null=True, editable=False)

    objects = models.Manager.from_queryset(PersonQuerySet)()

    search_fields = [
        index.AutocompleteField('first_name', partial_match=True),
        index.AutocompleteField('last_name', partial_match=True),
        index.FilterField('organization_new'),
    ]

    class Meta:
        verbose_name = _('person')
        verbose_name_plural = _('people')
        ordering = ('last_name', 'first_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIXME: This is hacky
        field = self._meta.get_field('image_cropping')
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
                self.image.save('avatar.jpg', io.BytesIO(photo))
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

    def get_avatar_url(self, request, size=None):
        if not request or not self.image:
            return None

        try:
            with self.image.open() as file:  # noqa
                pass
        except FileNotFoundError:
            logger.error('Avatar file for %s not found' % self)
            return None

        if size is None:
            url = self.image.url
        else:
            m = re.match(r'(\d+)?(x(\d+))?', size)
            if not m:
                raise ValueError('Invalid size argument (should be "<width>x<height>")')
            width, _, height = m.groups()

            dim = determine_image_dim(self.image_width, self.image_height, width, height)

            tn_args = {
                'size': dim,
            }
            if self.image_cropping:
                tn_args['focal_point'] = Rect(*[int(x) for x in self.image_cropping.split(',')])
                tn_args['crop'] = 30

            out_image = get_thumbnailer(self.image).get_thumbnail(tn_args)
            url = out_image.url

        return request.build_absolute_uri(url)

    def save(self, *args, **kwargs):
        old_cropping = self.image_cropping
        ret = super().save(*args, **kwargs)
        if self.image and not old_cropping:
            self.update_focal_point()
            if self.image_cropping != old_cropping:
                super().save(update_fields=['image_cropping'])

        user = self.create_corresponding_user()
        if self.user != user:
            self.user = user
            super().save(update_fields=['user'])

        return ret

    def get_admin_client(self):
        user = self.get_corresponding_user()

        plans = None
        if user is not None:
            # FIXME: Determine based on social_auth of last login

            plans = user.get_adminable_plans()
            if len(plans) < 1:
                raise Exception('No adminable plans for %s [Person-%d]' % (self.email, self.id))
        else:
            plans = set()
            plans.update(list(self.contact_for_actions.all().values_list('plan', flat=True).distinct()))
            indicators = self.contact_for_indicators.all()
            for ind in indicators:
                plans.update(ind.plans.all())

        if plans:
            clients = Client.objects.filter(plans__plan__in=plans).distinct()
            if len(clients) != 1:
                raise Exception('Invalid number of clients found for %s [Person-%d]: %d' % (
                    self.email, self.id, len(clients))
                )
            client = clients[0]
        else:
            # Match based on email domain
            email_domain = self.email.split('@')[1]
            clients = Client.objects.filter(email_domains__domain=email_domain.lower())
            if len(clients) != 1:
                raise Exception('Unable to find client for email %s [Person-%d]' % (
                    self.email, self.id)
                )
            client = clients[0]

        return client

    def get_notification_context(self, plan=None):
        client = self.get_admin_client()
        admin_url = client.get_admin_url()
        out = dict(
            first_name=self.first_name,
            last_name=self.last_name,
            admin_url=admin_url
        )

        logo = client.logo
        if logo is None:
            out['logo_url'] = None
            out['logo_height'] = None
            out['logo_width'] = None
            out['logo_alt'] = None
        else:
            rendition = logo.get_rendition('max-200x50')
            out['logo_url'] = admin_url + rendition.url
            out['logo_height'] = rendition.height
            out['logo_width'] = rendition.width
            out['logo_alt'] = logo.title

        return out

    def get_corresponding_user(self):
        if self.user:
            return self.user

        return User.objects.filter(email__iexact=self.email).first()

    def create_corresponding_user(self):
        user = self.get_corresponding_user()
        email = self.email.lower()
        if not user:
            user = User(
                email=email,
                uuid=uuid.uuid4(),
            )
            user.set_password(str(uuid.uuid4()))

        user.first_name = self.first_name
        user.last_name = self.last_name
        if user.email != email:
            user.email = email
        user.save()
        return user

    def __str__(self):
        return "%s %s" % (self.first_name, self.last_name)


# Override wagtail default avatar_url templatetag (registered in people/apps.py)
def avatar_url(context, user, size=50):
    if user is None:
        return wagtail_avatar_url(user, size)

    person = user.get_corresponding_person()
    if person is not None:
        url = person.get_avatar_url(context['request'], '%dx%d' % (size, size))
        if url:
            return url
    return wagtail_avatar_url(user, size)
