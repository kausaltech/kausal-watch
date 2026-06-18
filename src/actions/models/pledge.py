from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar, Self

import reversion
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from wagtail import blocks
from wagtail.fields import RichTextField, StreamField
from wagtail.models import TranslatableMixin
from wagtail.models.i18n import Locale

from modelsearch import index

from kausal_common.i18n.helpers import convert_language_code
from kausal_common.models.types import ModelManager

from aplans.utils import PlanRelatedModelQuerySet, PlanRelatedOrderedModel

from pages.blocks import LargeImageBlock, QuestionAnswerBlock
from search.models import SearchableModel

from .attributes import ModelWithAttributes
from .plan import Plan

if TYPE_CHECKING:
    from typing import Any

    from django.db.models import Manager
    from modelcluster.fields import PK
    from wagtail.fields import StreamValue

    from kausal_common.models.types import FK, M2MQS, RevMany
    from kausal_common.users import UserOrAnon

    from actions.attributes import AttributeFieldPanel, AttributeType
    from actions.models.action import Action, ActionQuerySet
    from images.models import AplansImage


class PledgeQuerySet(PlanRelatedModelQuerySet['Pledge']):
    def visible_for_user(self, user: UserOrAnon, plan: Plan):
        """Filter pledges visible to the given user for the given plan."""
        qs = self.filter(plan=plan)
        # For now, all pledges in a plan are visible to all users
        # In the future, we may add visibility restrictions
        return qs

    def for_plan(self, plan: Plan):
        """Filter by plan."""
        return self.filter(plan=plan)


# Manager configuration
if TYPE_CHECKING:

    class PledgeManager(ModelManager['Pledge', PledgeQuerySet]):
        def for_plan(self, plan: Plan) -> PledgeQuerySet: ...
        def visible_for_user(self, user: UserOrAnon, plan: Plan) -> PledgeQuerySet: ...

else:
    PledgeManager = ModelManager.from_queryset(PledgeQuerySet)


@reversion.register(follow=['pledge_action_through'] + ModelWithAttributes.REVERSION_FOLLOW)
class Pledge(
    PlanRelatedOrderedModel,
    ModelWithAttributes,
    SearchableModel[PledgeQuerySet],
    TranslatableMixin,
):
    """
    A Pledge represents a commitment that community members can make to support climate action.

    Pledges are part of the community engagement features and can be associated with
    actions from the plan. They include impact visualization fields
    to show the potential collective impact if many residents adopt the pledge.
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    plan: PK[Plan] = ParentalKey(
        'actions.Plan',
        on_delete=models.CASCADE,
        related_name='pledges',
        verbose_name=_('plan'),
    )
    name = models.CharField(
        max_length=300,
        verbose_name=_('name'),
    )
    slug = models.SlugField(
        max_length=100,
        verbose_name=_('slug'),
        help_text=_(
            "The unique part of the page's URL, usually based on the title. "
            'Use lowercase letters, numbers, and hyphens only (e.g., turn-off-electronics).'
        ),
    )
    description = models.TextField(
        max_length=300,
        blank=True,
        verbose_name=_('description'),
        help_text=_(
            'Brief description shown on pledge cards and at the top of the pledge page. '
            'Keep it under 2-3 sentences. Use the body content below for additional details.'
        ),
    )
    image: FK[AplansImage | None] = models.ForeignKey(
        'images.AplansImage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('image'),
    )

    # StreamField body with flexible content blocks
    body: StreamField[StreamValue | None] = StreamField(
        [
            ('paragraph', blocks.RichTextBlock()),
            ('question_answer', QuestionAnswerBlock()),
            ('large_image', LargeImageBlock()),
        ],
        blank=True,
        null=True,
        verbose_name=_('body content'),
        help_text=_('Detailed content about the pledge'),
    )

    # Impact visualization fields
    resident_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('number of residents committed'),
        help_text=_(
            'Choose a round number that makes the math easy but feels achievable (e.g., 50, 100, 200). '
            'This is used in the "If [X] residents commit..." messaging.'
        ),
    )
    impact_statement = RichTextField(
        max_length=150,
        blank=True,
        verbose_name=_('environmental impact at scale'),
        help_text=_(
            'Describe the total environmental benefit if this many residents commit. '
            'Include specific numbers and units. Start with "We save" or "We reduce" for consistency. '
            'Example: "We save 9,200kg CO₂e each year."'
        ),
    )
    local_equivalency = RichTextField(
        max_length=150,
        blank=True,
        verbose_name=_('local equivalency comparison'),
        help_text=_(
            'Translate the environmental impact into something relatable and specific to your community. '
            'Use local landmarks, familiar distances, or everyday activities. '
            'Start with "That\'s equivalent to" or "That\'s like" for consistency. '
            'Example: "That\'s equivalent to avoiding 575 round trips between City Hall and the waterfront."'
        ),
    )

    # Relationships
    actions: M2MQS[Action, PledgeActionThrough, ActionQuerySet] = ParentalManyToManyField(  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]
        'actions.Action',
        through='PledgeActionThrough',
        related_name='pledges',
        blank=True,
        verbose_name=_('actions'),
        help_text=_('Actions this pledge supports'),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        verbose_name=_('updated at'),
    )

    commitments: RevMany[PledgeCommitment]

    objects: ClassVar[PledgeManager] = PledgeManager()

    # Search configuration
    search_fields = [
        index.SearchField('name', boost=10),
        index.AutocompleteField('name'),
        index.SearchField('description'),
        index.SearchField('body'),
        index.FilterField('plan_id'),
    ]

    class Meta:
        verbose_name = _('pledge')
        verbose_name_plural = _('pledges')
        unique_together = [('plan', 'slug', 'locale'), ('translation_key', 'locale')]
        ordering = ['plan', 'order']

    def __str__(self) -> str:
        return self.name

    @staticmethod
    def get_locale_for_language_code(language_code: str) -> Locale:
        normalized_code = convert_language_code(language_code, 'wagtail')
        return Locale.objects.get(language_code__iexact=normalized_code)

    def get_translation_for_language(self, language_code: str | None) -> Pledge:
        if not language_code:
            return self

        normalized = convert_language_code(language_code, 'wagtail')
        locale = Locale.objects.filter(language_code__iexact=normalized).first()
        if locale is None and '-' in normalized:
            fallback_code = normalized.split('-', maxsplit=1)[0]
            locale = Locale.objects.filter(language_code__iexact=fallback_code).first()
        if locale is None:
            return self
        return self.get_translation_or_none(locale) or self

    def get_primary_translation(self) -> Pledge:
        primary_locale = self.get_locale_for_language_code(self.plan.primary_language)
        return self.get_translation_or_none(primary_locale) or self

    def get_attributes_source(self) -> Pledge:
        """Return the instance that holds authoritative attribute data (the primary translation)."""
        return self.get_primary_translation()

    def ensure_locale_copies(self) -> None:
        """Ensure locale copies exist for all plan languages."""
        if self.pk is None:
            return

        existing_locale_ids = set(self.get_translations(inclusive=True).values_list('locale_id', flat=True))
        action_ids = list(self.actions.values_list('id', flat=True))
        language_codes = [self.plan.primary_language, *self.plan.other_languages]

        for language_code in language_codes:
            locale = self.get_locale_for_language_code(language_code)
            if locale.id in existing_locale_ids:
                continue
            translation = self.copy_for_translation(locale)
            translation.uuid = uuid.uuid4()
            translation.save()
            if action_ids:
                translation.actions.set(action_ids)
            existing_locale_ids.add(locale.id)

    def handle_admin_save(self, context: dict | None = None) -> None:
        operation = (context or {}).get('operation')
        if operation != 'create':
            return
        self.ensure_locale_copies()

    @classmethod
    def get_attribute_types_for_plan(
        cls,
        plan: Plan,
        only_in_reporting_tab: bool = False,
        unless_in_reporting_tab: bool = False,  # noqa: ARG003
    ) -> list[AttributeType[Any]]:
        """Get all attribute types for Pledges in the given plan."""
        from django.contrib.contenttypes.models import ContentType

        from actions.attributes import AttributeType
        from actions.models import AttributeType as AttributeTypeModel

        if only_in_reporting_tab:
            return []

        pledge_ct = ContentType.objects.get_for_model(cls)
        plan_content_type = ContentType.objects.get_for_model(Plan)

        at_qs: models.QuerySet[AttributeTypeModel] = AttributeTypeModel.objects.filter(
            object_content_type=pledge_ct,
            scope_content_type=plan_content_type,
            scope_id=plan.id,
        )

        # Convert to wrapper objects
        return [AttributeType.from_model_instance(at) for at in at_qs]

    def get_editable_attribute_types(self, user: UserOrAnon) -> list[AttributeType[Any]]:
        """Get attribute types editable for this pledge and user."""
        from django.contrib.contenttypes.models import ContentType

        from actions.attributes import AttributeType
        from actions.models import AttributeType as AttributeTypeModel

        pledge_ct = ContentType.objects.get_for_model(Pledge)
        plan_ct = ContentType.objects.get_for_model(Plan)

        at_qs = AttributeTypeModel.objects.filter(
            object_content_type=pledge_ct,
            scope_content_type=plan_ct,
            scope_id=self.plan.pk,
        )

        attribute_types = (at for at in at_qs if at.is_instance_editable_by(user, self.plan, None))
        # Convert to wrapper objects
        return [AttributeType.from_model_instance(at) for at in attribute_types]

    def get_visible_attribute_types(self, user: UserOrAnon) -> list[AttributeType[Any]]:
        """Get attribute types visible for this pledge and user."""
        from django.contrib.contenttypes.models import ContentType

        from actions.attributes import AttributeType
        from actions.models import AttributeType as AttributeTypeModel

        pledge_ct = ContentType.objects.get_for_model(Pledge)
        plan_ct = ContentType.objects.get_for_model(Plan)

        at_qs = AttributeTypeModel.objects.filter(
            object_content_type=pledge_ct,
            scope_content_type=plan_ct,
            scope_id=self.plan.pk,
        )

        attribute_types = (at for at in at_qs if at.is_instance_visible_for(user, self.plan, None))
        # Convert to wrapper objects
        return [AttributeType.from_model_instance(at) for at in attribute_types]

    def get_attribute_panels(self, user):
        """
        Return attribute panels for the Pledge edit form.

        Returns a tuple (main_panels, i18n_panels), where:
        - main_panels: list of panels for the main Attributes tab
        - i18n_panels: dict mapping language code to list of panels for that language's tab
        """
        main_panels = []
        i18n_panels: dict[str, list[AttributeFieldPanel[Any]]] = {}
        attribute_types = self.get_visible_attribute_types(user)
        plan = user.get_active_admin_plan()
        for attribute_type in attribute_types:
            main, i18n = attribute_type.get_panels(user, plan, self)
            main_panels.extend(main)
            for lang, lang_panels in i18n.items():
                i18n_panels.setdefault(lang, []).extend(lang_panels)
        return (main_panels, i18n_panels)


def _generate_user_token() -> str:
    return secrets.token_urlsafe(48)


def _get_user_token_pepper() -> bytes:
    """
    Derive a per-app HMAC key from SECRET_KEY.

    Scoping with a label prevents the pepper from being equivalent to keys used
    elsewhere with SECRET_KEY. Rotating SECRET_KEY rotates all user_token hashes,
    invalidating outstanding bearer credentials, which is the intended behavior.
    """
    return hashlib.sha256(b'kausal-watch:public_user_token_pepper:' + settings.SECRET_KEY.encode()).digest()


def hash_user_token(raw_token: str) -> str:
    """Return the HMAC-SHA256 hex digest of a raw user token."""
    return hmac.new(_get_user_token_pepper(), raw_token.encode(), hashlib.sha256).hexdigest()


PIN_LENGTH = 6
PIN_TTL = timedelta(minutes=10)
PIN_MAX_ATTEMPTS = 5
SIGNIN_COOLDOWN = timedelta(seconds=30)


def _generate_pin() -> str:
    return f'{secrets.randbelow(10**PIN_LENGTH):0{PIN_LENGTH}d}'


def hash_pin(raw_pin: str, salt: str) -> str:
    return hashlib.sha256((salt + raw_pin).encode()).hexdigest()


@reversion.register(exclude=['user_token'])
class PublicUser(models.Model):
    """
    A public-facing user identity.

    PublicUser represents community members who participate in public-facing
    features such as pledges without requiring a full user account. Anonymous
    users are identified by uuid; user_token is set only after the user
    verifies an email (i.e., signs up), and is then used as a bearer
    credential for authenticated requests.
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('user data'),
        help_text=_('Freeform key-value data about the user (e.g., zip_code)'),
    )
    user_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name=_('user token'),
        help_text=_('Opaque secret used as a bearer credential after the user signs up.'),
    )
    email = models.EmailField(
        null=True,
        blank=True,
        unique=True,
        verbose_name=_('email'),
        help_text=_('Set when the user signs up; used for PIN-based authentication.'),
    )
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('terms accepted at'),
    )
    marketing_consented_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('marketing consented at'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('created at'),
    )

    objects: ClassVar[Manager[Self]]

    commitments: RevMany[PledgeCommitment]
    sign_in_attempt: PublicUserSignInAttempt | None

    class Meta:
        verbose_name = _('public user')
        verbose_name_plural = _('public users')

    def __str__(self) -> str:
        return self.email or str(self.uuid)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def regenerate_user_token(self) -> str:
        """
        Mint a new raw bearer token, store its HMAC hash on the row, and return the raw value.

        The raw token is returned to the caller exactly once (typically to the
        client via a mutation payload). The database only ever holds the hash.
        """
        raw_token = _generate_user_token()
        self.user_token = hash_user_token(raw_token)
        self.save(update_fields=['user_token'])
        return raw_token


@reversion.register(exclude=['pin_hash', 'pin_salt'])
class PublicUserSignInAttempt(models.Model):
    """
    State held between a SignIn/SignUp call and a successful VerifyPin.

    Created when a user requests a PIN via SignIn or SignUp; consumed by
    VerifyPin. One attempt per user at a time; a new SignIn/SignUp replaces
    the previous one. The raw PIN is only ever known to the user; the database
    stores its sha256(salt + pin). The anon_uuid carries the merge intent
    captured at sign-in time, so VerifyPin can merge the anonymous session's
    pledges into the email-verified account even when verification happens on
    a different device than sign-in.
    """

    public_user: FK[PublicUser] = models.OneToOneField(
        'PublicUser',
        on_delete=models.CASCADE,
        related_name='sign_in_attempt',
    )
    pin_hash = models.CharField(max_length=64, editable=False)
    pin_salt = models.CharField(max_length=32, editable=False)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    anon_uuid = models.UUIDField(null=True, blank=True, editable=False)

    objects: ClassVar[models.Manager[PublicUserSignInAttempt]]

    class Meta:
        verbose_name = _('public user sign-in attempt')
        verbose_name_plural = _('public user sign-in attempts')

    def __str__(self) -> str:
        return f'Sign-in attempt for {self.public_user}'

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def attempts_exhausted(self) -> bool:
        return self.attempts >= PIN_MAX_ATTEMPTS

    @classmethod
    def create_for(cls, public_user: PublicUser, anon_uuid: uuid.UUID | None = None) -> tuple[PublicUserSignInAttempt, str]:
        """
        Generate a fresh PIN for the given user, replacing any existing attempt.

        Returns the new attempt plus the raw PIN. The raw PIN must be delivered
        to the user (e.g., by email) and is not stored anywhere in the database.
        """
        raw_pin = _generate_pin()
        salt = secrets.token_hex(16)
        now = timezone.now()
        attempt, _ = cls.objects.update_or_create(
            public_user=public_user,
            defaults={
                'pin_hash': hash_pin(raw_pin, salt),
                'pin_salt': salt,
                'issued_at': now,
                'expires_at': now + PIN_TTL,
                'attempts': 0,
                'anon_uuid': anon_uuid,
            },
        )
        return attempt, raw_pin

    def verify(self, raw_pin: str) -> bool:
        """
        Validate a raw PIN against the stored hash.

        Increments the attempt counter on every call. Returns False if the
        attempt is expired, attempts are exhausted, or the PIN doesn't match.
        """
        self.attempts += 1
        self.save(update_fields=['attempts'])
        if self.is_expired or self.attempts_exhausted:
            return False
        expected = hash_pin(raw_pin, self.pin_salt)
        return hmac.compare_digest(expected, self.pin_hash)


@reversion.register()
class PledgeCommitment(models.Model):
    """
    A commitment made by a PublicUser to a specific Pledge.

    Tracks when anonymous community members commit to supporting climate action
    through pledges.
    """

    pledge: FK[Pledge] = models.ForeignKey(
        Pledge,
        on_delete=models.CASCADE,
        related_name='commitments',
        verbose_name=_('pledge'),
    )
    public_user: FK[PublicUser] = models.ForeignKey(
        PublicUser,
        on_delete=models.CASCADE,
        related_name='commitments',
        verbose_name=_('public user'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('created at'),
    )

    objects: ClassVar[Manager[Self]]

    class Meta:
        verbose_name = _('pledge commitment')
        verbose_name_plural = _('pledge commitments')
        unique_together = [('pledge', 'public_user')]

    def __str__(self) -> str:
        return f'{self.public_user} - {self.pledge}'


@reversion.register()
class PledgeActionThrough(models.Model):
    """Through model for Pledge-Action many-to-many relationship."""

    objects: ClassVar[Manager[Self]]

    pledge: FK[Pledge] = models.ForeignKey(
        Pledge,
        related_name='pledge_action_through',
        on_delete=models.CASCADE,
    )
    action: FK[Action] = models.ForeignKey(
        'actions.Action',
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = [('pledge', 'action')]
        verbose_name = _('pledge action')
        verbose_name_plural = _('pledge actions')

    def __str__(self) -> str:
        return f'{self.pledge} - {self.action}'
