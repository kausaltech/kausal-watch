from __future__ import annotations

import contextlib
import copy
import hashlib
import logging
import re
import uuid
from typing import TYPE_CHECKING, ClassVar

import reversion
from django.contrib.auth.models import AnonymousUser
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from modeltrans.manager import MultilingualQuerySet
from wagtail.admin.templatetags.wagtailadmin_tags import avatar_url as wagtail_avatar_url
from wagtail.images.rect import Rect

import requests
from easy_thumbnails.files import get_thumbnailer  # type: ignore
from sentry_sdk import capture_exception

from kausal_common.models.types import MLModelManager, RevManyToManyQS
from kausal_common.people.models import BasePerson

from aplans.utils import PlanDefaultsModel

from actions.models import ActionContactPerson, PlanFeatures
from admin_site.models import Client
from orgs.models import Organization, OrganizationMetadataAdmin, OrganizationQuerySet
from users.models import User

if TYPE_CHECKING:
    from kausal_common.models.types import M2M, RevMany

    from aplans.types import UserOrAnon, WatchRequest

    from actions.models.action import Action
    from actions.models.plan import Plan, PlanPublicSiteViewer
    from indicators.models import Indicator
    from orgs.models import OrganizationPlanAdmin
    from users.models import User as UserModel


logger = logging.getLogger(__name__)
#User: type[UserModel] = get_user_model()  # type: ignore

def determine_image_dim(image_width, image_height, width, height):
    for name in ('width', 'height'):
        x = locals()[name]
        if x is None:
            continue
        try:
            x = int(x)
            if x <= 0:
                raise ValueError()  # noqa: TRY301
            if x > 4000:
                raise ValueError()  # noqa: TRY301
        except (ValueError, TypeError):
            raise ValueError("invalid %s dimension: %s" % (name, x)) from None

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


class PersonQuerySet(MultilingualQuerySet['Person']):
    def available_for_plan(self, plan: Plan, include_contact_persons=False):
        """Return persons from an organization related to the plan."""
        related = Organization.objects.filter(id=plan.organization_id) | plan.related_organizations.all()
        q = Q(pk__in=[])  # always false; Q() doesn't cut it; https://stackoverflow.com/a/39001190/14595546
        for org in related:
            q |= Q(organization__path__startswith=org.path)
        if include_contact_persons:
            q |= Q(id__in=ActionContactPerson.objects.filter(action__plan=plan).values_list('person'))
        return self.filter(q)

    def is_action_contact_person(self, plan: Plan):
        return self.filter(contact_for_actions__plan=plan).distinct()

    def visible_for_user(self, user: UserModel | None, plan: Plan):
        if plan.features.public_contact_persons:
            return self
        if user is None or not user.is_authenticated or not user.can_access_public_site(plan):
            return self.none()
        return self


if TYPE_CHECKING:
    _PersonManager = models.Manager.from_queryset(PersonQuerySet)
    class PersonManager(MLModelManager['Person', PersonQuerySet], _PersonManager): ...  # pyright: ignore
    del _PersonManager
else:
    PersonManager = MLModelManager.from_queryset(PersonQuerySet)

DEFAULT_AVATAR_SIZE = 360

@reversion.register()
class Person(BasePerson, PlanDefaultsModel):
    participated_in_training = models.BooleanField(
        null=True, default=False, verbose_name=_('participated in training'),
        help_text=_('Set to keep track who have attended training sessions'),
    )

    contact_for_actions_unordered: M2M[Action, ActionContactPerson] = models.ManyToManyField(
        'actions.Action',
        through='actions.ActionContactPerson',
        blank=True,
        verbose_name=_('contact for actions'),
    )

    objects: ClassVar[PersonManager] = PersonManager()  # pyright: ignore

    public_fields = BasePerson.public_fields + [
        'participated_in_training',
    ]

    # Type annotations for related models etc.
    id: int
    contact_for_actions: RevMany[Action]
    contact_for_indicators: RevMany[Indicator]
    organization_plan_admins: RevMany[OrganizationPlanAdmin]
    general_admin_plans: RevMany[Plan]
    plans_with_public_site_access: RevMany[PlanPublicSiteViewer]
    actioncontactperson_set: RevMany[ActionContactPerson]
    metadata_adminable_organizations: RevManyToManyQS[Organization, OrganizationMetadataAdmin, OrganizationQuerySet]
    organization_id: int
    created_by_id: int

    def initialize_plan_defaults(self, plan: Plan):
        self.organization = plan.organization

    def download_avatar(self):
        url = None
        if self.email.endswith('@hel.fi'):
            url = f'https://api.hel.fi/avatar/{self.email}?s={DEFAULT_AVATAR_SIZE}&d=404'
        else:
            md5_hash = hashlib.md5(self.email.encode('utf8'), usedforsecurity=False).hexdigest()
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

    def get_avatar_url(self, request: WatchRequest, size: str | None = None) -> str | None:
        if not self.image:
            return None

        try:
            with self.image.open():
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
            elif user is not None and not user.is_superuser:
                logger.warning('Invalid number of clients found for %s [Person-%d]: %d' % (
                    self.email, self.id, len(clients),  # pyright: ignore
                ))
        if not client:
            client = self.get_client_for_email_domain()
        return client

    def get_notification_context(self):
        client = self.get_admin_client()
        if client is None:
            raise ValueError('Unable to find client for person when sending notifications')
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
                with contextlib.suppress(User.DoesNotExist):
                    user = User.objects.get(email__iexact=email, is_active=False)
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
            if isinstance(user, AnonymousUser):
                return False
            if user is None or not user.is_authenticated or not user.can_access_public_site(plan):
                return False
        return True

    def is_public_site_viewer(self, plan: Plan | None = None) -> bool:
        if plan is None:
            return self.plans_with_public_site_access.exists()
        return plan.pk in self.plans_with_public_site_access.values_list('plan_id', flat=True)

    def get_redacted_copy(self, plan: Plan):
        """
        Return a copy of self with redacted information according to the configuration of the given plan.

        You better not save the returned object.
        """
        if plan.features.contact_persons_public_data in (
            PlanFeatures.ContactPersonsPublicData.ALL,
            PlanFeatures.ContactPersonsPublicData.ALL_FOR_AUTHENTICATED,
        ):
            return copy.copy(self)
        if plan.features.contact_persons_public_data == PlanFeatures.ContactPersonsPublicData.NAME:
            return Person(
                id=self.pk,  # if we omit this, GraphQL will complain that we return null for nun-nullable `id` fields
                first_name=self.first_name,
                last_name=self.last_name,
                title=self.title,
                organization=self.organization,
            )
        if plan.features.contact_persons_public_data == PlanFeatures.ContactPersonsPublicData.NONE:
            return Person(id=self.pk)
        raise AssertionError("Unexpected value for PlanFeatures.contact_persons_public_data")

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
