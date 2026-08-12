from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar

import reversion
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Any

    from kausal_common.models.types import FK, RevMany

    from actions.models.pledge import PledgeCommitment
    from admin_site.models import Client


def _generate_user_token() -> str:
    return secrets.token_urlsafe(48)


def _get_user_token_pepper() -> bytes:
    """Derive an HMAC key for user token hashing from SECRET_KEY."""
    return hashlib.sha256(b'kausal-watch:public_user_token_pepper:' + settings.SECRET_KEY.encode()).digest()


def hash_user_token(raw_token: str) -> str:
    """Return the HMAC-SHA256 hex digest of a raw user token."""
    return hmac.new(_get_user_token_pepper(), raw_token.encode(), hashlib.sha256).hexdigest()


PIN_LENGTH = 6
PIN_TTL = timedelta(minutes=10)
PIN_MAX_ATTEMPTS = 5
SIGNIN_COOLDOWN = timedelta(seconds=30)
SIGNUP_COOLDOWN = timedelta(seconds=5)


def _generate_pin() -> str:
    return f'{secrets.randbelow(10**PIN_LENGTH):0{PIN_LENGTH}d}'


def _get_pin_pepper() -> bytes:
    """Derive an HMAC key for PIN hashing from SECRET_KEY."""
    return hashlib.sha256(b'kausal-watch:public_user_pin_pepper:' + settings.SECRET_KEY.encode()).digest()


def hash_pin(raw_pin: str, salt: str) -> str:
    return hmac.new(_get_pin_pepper(), (salt + raw_pin).encode(), hashlib.sha256).hexdigest()


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
        verbose_name=_('email'),
        help_text=_('Set when the user signs up; used for PIN-based authentication.'),
    )
    client: FK[Client | None] = models.ForeignKey(
        'admin_site.Client',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='public_users',
        verbose_name=_('client'),
        help_text=_('Tenant this account belongs to. Required for authed rows; null for anonymous rows.'),
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
    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('email verified at'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('created at'),
    )
    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='public_user')

    objects: ClassVar[models.Manager[PublicUser]]

    commitments: RevMany[PledgeCommitment]
    sign_in_attempt: PublicUserSignInAttempt | None

    class Meta:
        app_label = 'actions'
        verbose_name = _('public user')
        verbose_name_plural = _('public users')
        constraints = [
            models.UniqueConstraint(
                fields=['email', 'client'],
                condition=models.Q(email__isnull=False),
                name='unique_public_user_email_per_client',
            ),
            models.CheckConstraint(
                condition=models.Q(email__isnull=True) | models.Q(client__isnull=False),
                name='public_user_email_requires_client',
            ),
        ]

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

    public_user: FK[PublicUser | None] = models.OneToOneField(
        PublicUser,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='sign_in_attempt',
    )
    client: FK[Client | None] = models.ForeignKey(
        'admin_site.Client',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='+',
    )
    email = models.EmailField(null=True, blank=True)
    pending_terms_accepted_at = models.DateTimeField(null=True, blank=True)
    pending_marketing_consented_at = models.DateTimeField(null=True, blank=True)
    pin_hash = models.CharField(max_length=64, editable=False)
    pin_salt = models.CharField(max_length=32, editable=False)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    anon_uuid = models.UUIDField(null=True, blank=True, editable=False)

    objects: ClassVar[models.Manager[PublicUserSignInAttempt]]

    class Meta:
        app_label = 'actions'
        verbose_name = _('public user sign-in attempt')
        verbose_name_plural = _('public user sign-in attempts')
        constraints = [
            models.UniqueConstraint(
                fields=['email', 'client'],
                condition=models.Q(public_user__isnull=True),
                name='unique_pending_signup_email',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(public_user__isnull=False)
                    | (
                        models.Q(email__isnull=False)
                        & models.Q(client__isnull=False)
                        & models.Q(pending_terms_accepted_at__isnull=False)
                    )
                ),
                name='attempt_has_user_or_pending_signup',
            ),
        ]

    def __str__(self) -> str:
        if self.public_user is not None:
            return f'Sign-in attempt for {self.public_user}'
        return f'Pending sign-up for {self.email}'

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def attempts_exhausted(self) -> bool:
        return self.attempts >= PIN_MAX_ATTEMPTS

    @staticmethod
    def _fresh_attempt_state(anon_uuid: uuid.UUID | None) -> tuple[dict[str, Any], str]:
        raw_pin = _generate_pin()
        salt = secrets.token_hex(16)
        now = timezone.now()
        return {
            'pin_hash': hash_pin(raw_pin, salt),
            'pin_salt': salt,
            'issued_at': now,
            'expires_at': now + PIN_TTL,
            'attempts': 0,
            'anon_uuid': anon_uuid,
        }, raw_pin

    @classmethod
    def create_for_signin(
        cls,
        public_user: PublicUser,
        anon_uuid: uuid.UUID | None = None,
    ) -> tuple[PublicUserSignInAttempt, str]:
        """
        Generate a fresh PIN for an existing (signed-up) user.

        Returns the new attempt plus the raw PIN. The raw PIN must be delivered
        to the user (e.g., by email) and is not stored anywhere in the database.
        """
        base, raw_pin = cls._fresh_attempt_state(anon_uuid)
        attempt, _ = cls.objects.update_or_create(
            public_user=public_user,
            defaults={
                **base,
                'email': None,
                'client': public_user.client,
                'pending_terms_accepted_at': None,
                'pending_marketing_consented_at': None,
            },
        )
        return attempt, raw_pin

    @classmethod
    def create_for_signup(
        cls,
        email: str,
        client: Client,
        terms_accepted_at: datetime,
        marketing_consented_at: datetime | None,
        anon_uuid: uuid.UUID | None = None,
    ) -> tuple[PublicUserSignInAttempt, str]:
        """
        Generate a fresh PIN for a pending sign-up (no PublicUser yet).

        Consent timestamps are stored on the attempt and applied to the
        PublicUser at VerifyPin time, so the row only carries consent for a
        verifier that actually controls the mailbox. Replaces any existing
        pending attempt for the same (email, client).
        """
        base, raw_pin = cls._fresh_attempt_state(anon_uuid)
        existing = cls.objects.filter(email=email, client=client, public_user__isnull=True).first()
        defaults = {
            **base,
            'client': client,
            'pending_terms_accepted_at': terms_accepted_at,
            'pending_marketing_consented_at': marketing_consented_at,
        }
        if existing is not None:
            for field, value in defaults.items():
                setattr(existing, field, value)
            existing.save()
            return existing, raw_pin
        attempt = cls.objects.create(
            public_user=None,
            email=email,
            **defaults,
        )
        return attempt, raw_pin

    def verify(self, raw_pin: str) -> bool:
        """
        Validate a raw PIN against the stored hash.

        Increments the attempt counter atomically on every call. Returns False
        if the attempt is expired, the counter is past PIN_MAX_ATTEMPTS, or
        the PIN doesn't match.
        """
        PublicUserSignInAttempt.objects.filter(pk=self.pk).update(attempts=models.F('attempts') + 1)
        self.refresh_from_db(fields=['attempts'])
        if self.is_expired or self.attempts > PIN_MAX_ATTEMPTS:
            return False
        expected = hash_pin(raw_pin, self.pin_salt)
        return hmac.compare_digest(expected, self.pin_hash)
