from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError
from django.utils import timezone, translation
from wagtail.models import Locale

import pytest

from actions.models import Pledge, PledgeCommitment, PublicUser, PublicUserSignInAttempt
from actions.models.attributes import AttributeText, AttributeType as AttributeTypeModel
from actions.models.pledge import PIN_MAX_ATTEMPTS, hash_pin, hash_user_token
from actions.public_user_auth import send_pin_email
from actions.tests.factories import ActionFactory, PlanFactory, PledgeFactory
from notifications.models import BaseTemplate

pytestmark = pytest.mark.django_db


class TestPledge:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_creation(self):
        """Test that a Pledge can be created with all fields."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='Test Pledge',
            slug='test-pledge',
            description='A test pledge description',
            resident_count=100,
            impact_statement='We save 100kg CO₂e each year',
            local_equivalency="That's equivalent to 10 round trips",
        )

        assert pledge.name == 'Test Pledge'
        assert pledge.slug == 'test-pledge'
        assert pledge.plan == self.plan
        assert pledge.resident_count == 100

    def test_pledge_slug_unique_per_plan(self):
        """Test that pledge slugs must be unique within a plan."""
        Pledge.objects.create(
            plan=self.plan,
            name='First Pledge',
            slug='test-pledge',
        )

        # Creating another pledge with same slug in same plan should raise IntegrityError
        with pytest.raises(IntegrityError):
            Pledge.objects.create(
                plan=self.plan,
                name='Second Pledge',
                slug='test-pledge',
            )

    def test_pledge_slug_unique_across_different_plans(self):
        """Test that the same slug can be used in different plans."""
        other_plan = PlanFactory.create()

        pledge1 = Pledge.objects.create(
            plan=self.plan,
            name='First Pledge',
            slug='same-slug',
        )
        pledge2 = Pledge.objects.create(
            plan=other_plan,
            name='Second Pledge',
            slug='same-slug',
        )

        assert pledge1.slug == pledge2.slug
        assert pledge1.plan != pledge2.plan

    def test_feature_flag_in_public_fields(self):
        """Test that enable_community_engagement is in public_fields."""
        assert 'enable_community_engagement' in self.plan.features.public_fields

    def test_feature_flag_can_be_toggled(self):
        """Test that the feature flag can be enabled and disabled."""
        self.plan.features.enable_community_engagement = False
        self.plan.features.save()
        self.plan.features.refresh_from_db()
        assert self.plan.features.enable_community_engagement is False

        self.plan.features.enable_community_engagement = True
        self.plan.features.save()
        self.plan.features.refresh_from_db()
        assert self.plan.features.enable_community_engagement is True


class TestPledgeLocaleTranslations:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create(
            primary_language='en',
            other_languages=['fi', 'sv'],
        )
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_slug_can_repeat_across_locales_in_same_plan(self):
        """Test that the same slug is allowed across locale copies of a pledge."""
        primary_pledge = PledgeFactory.create(
            plan=self.plan,
            slug='shared-slug',
            name='Primary name',
        )
        fi_locale, _ = Locale.objects.get_or_create(language_code='fi')
        fi_pledge = primary_pledge.copy_for_translation(fi_locale)
        fi_pledge.name = 'Suomenkielinen nimi'
        fi_pledge.uuid = uuid.uuid4()
        fi_pledge.save()

        assert primary_pledge.slug == fi_pledge.slug
        assert primary_pledge.locale != fi_pledge.locale

    def test_get_primary_translation_returns_primary_locale_instance(self):
        """Test that get_primary_translation resolves locale copies back to primary locale."""
        primary_pledge = PledgeFactory.create(plan=self.plan, name='Primary')
        fi_locale, _ = Locale.objects.get_or_create(language_code='fi')
        fi_pledge = primary_pledge.copy_for_translation(fi_locale)
        fi_pledge.name = 'Suomi'
        fi_pledge.uuid = uuid.uuid4()
        fi_pledge.save()

        assert fi_pledge.get_primary_translation().id == primary_pledge.id

    def test_get_translation_for_language_returns_requested_translation(self):
        """Test that get_translation_for_language returns the requested locale translation."""
        primary_pledge = PledgeFactory.create(plan=self.plan, name='Primary')
        fi_locale, _ = Locale.objects.get_or_create(language_code='fi')
        fi_pledge = primary_pledge.copy_for_translation(fi_locale)
        fi_pledge.name = 'Suomi'
        fi_pledge.uuid = uuid.uuid4()
        fi_pledge.save()

        translation = primary_pledge.get_translation_for_language('fi')
        assert translation.id == fi_pledge.id
        assert translation.name == 'Suomi'

    def test_get_translation_for_language_falls_back_when_translation_missing(self):
        """Test that get_translation_for_language falls back to the current pledge when missing."""
        primary_pledge = PledgeFactory.create(plan=self.plan, name='Primary')

        translation = primary_pledge.get_translation_for_language('de')
        assert translation.id == primary_pledge.id
        assert translation.name == 'Primary'

    def test_ensure_locale_copies_creates_missing_plan_language_rows(self):
        """Test that ensure_locale_copies creates locale copies for all plan languages."""
        action = ActionFactory.create(plan=self.plan)
        primary_pledge = PledgeFactory.create(plan=self.plan, actions=[action])

        primary_pledge.ensure_locale_copies()

        locale_codes = sorted(
            primary_pledge.get_translations(inclusive=True).values_list('locale__language_code', flat=True),
        )
        assert locale_codes == ['en', 'fi', 'sv']
        for pledge_translation in primary_pledge.get_translations(inclusive=True):
            assert list(cast('Pledge', pledge_translation).actions.values_list('id', flat=True)) == [action.id]

    def test_plan_language_change_creates_missing_locale_copies_for_existing_pledges(self):
        """Test that changing plan languages syncs pledge locale copies."""
        plan = PlanFactory.create(primary_language='en', other_languages=['fi'])
        primary_pledge = PledgeFactory.create(plan=plan, name='Primary')

        plan.other_languages = ['fi', 'sv']
        plan.save(update_fields=['other_languages'])

        locale_codes = sorted(
            primary_pledge.get_translations(inclusive=True).values_list('locale__language_code', flat=True),
        )
        assert locale_codes == ['en', 'fi', 'sv']


class TestPledgeActionRelationship:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_can_have_multiple_actions(self):
        """Test that a pledge can be associated with multiple actions."""
        action1 = ActionFactory.create(plan=self.plan)
        action2 = ActionFactory.create(plan=self.plan)
        action3 = ActionFactory.create(plan=self.plan)

        pledge = PledgeFactory.create(plan=self.plan, actions=[action1, action2, action3])

        assert set(pledge.actions.all()) == {action1, action2, action3}

    def test_action_can_be_in_multiple_pledges(self):
        """Test that an action can be associated with multiple pledges."""
        action = ActionFactory.create(plan=self.plan)

        pledge1 = PledgeFactory.create(plan=self.plan, actions=[action])
        pledge2 = PledgeFactory.create(plan=self.plan, actions=[action])

        assert action in pledge1.actions.all()
        assert action in pledge2.actions.all()

    def test_pledge_actions_unique_together(self):
        """Test that the same action cannot be added twice to the same pledge."""
        action = ActionFactory.create(plan=self.plan)
        pledge = PledgeFactory.create(plan=self.plan)

        # Add action first time
        pledge.actions.add(action)
        assert pledge.actions.count() == 1

        # Adding same action again should not create duplicate
        pledge.actions.add(action)
        assert pledge.actions.count() == 1


class TestPledgeOrdering:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_ordering_by_plan_and_order(self):
        """Test that pledges are ordered by plan and then by order field."""
        pledge3 = PledgeFactory.create(plan=self.plan, order=3)
        pledge1 = PledgeFactory.create(plan=self.plan, order=1)
        pledge2 = PledgeFactory.create(plan=self.plan, order=2)

        # Use explicit order_by to verify ordering
        pledges = list(Pledge.objects.filter(plan=self.plan).order_by('order'))

        assert pledges == [pledge1, pledge2, pledge3]
        assert pledges[0].order == 1
        assert pledges[1].order == 2
        assert pledges[2].order == 3

    def test_pledge_order_can_be_changed(self):
        """Test that pledge order can be modified."""
        pledge = PledgeFactory.create(plan=self.plan, order=1)

        pledge.order = 5
        pledge.save()
        pledge.refresh_from_db()

        assert pledge.order == 5


@pytest.mark.django_db
class TestPledgeQuerySet:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_for_plan_filters_by_plan(self):
        """Test that for_plan queryset method filters by plan."""
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()

        pledge1 = PledgeFactory.create(plan=self.plan)
        pledge2 = PledgeFactory.create(plan=other_plan)

        qs = Pledge.objects.for_plan(self.plan)

        assert pledge1 in qs
        assert pledge2 not in qs

    def test_visible_for_user_filters_by_plan(self):
        """Test that visible_for_user queryset method filters by plan."""
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()

        pledge1 = PledgeFactory.create(plan=self.plan)
        pledge2 = PledgeFactory.create(plan=other_plan)

        # Using anonymous user since all pledges are currently visible to all users
        qs = Pledge.objects.visible_for_user(AnonymousUser(), self.plan)

        assert pledge1 in qs
        assert pledge2 not in qs


class TestPledgeOptionalFields:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_with_minimal_fields(self):
        """Test that a pledge can be created with only required fields."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='Minimal Pledge',
            slug='minimal-pledge',
        )

        assert pledge.name == 'Minimal Pledge'
        assert pledge.description == ''
        assert pledge.resident_count is None
        assert pledge.impact_statement == ''
        assert pledge.local_equivalency == ''
        assert pledge.image is None

    def test_pledge_with_empty_body(self):
        """Test that a pledge can have an empty StreamField body."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='Empty Body Pledge',
            slug='empty-body-pledge',
        )

        # StreamField body should be empty/None by default
        assert pledge.body is None or len(pledge.body) == 0

    def test_pledge_uuid_is_auto_generated(self):
        """Test that UUID is automatically generated for new pledges."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='UUID Test Pledge',
            slug='uuid-test-pledge',
        )

        assert pledge.uuid is not None
        # UUID should be unique
        pledge2 = Pledge.objects.create(
            plan=self.plan,
            name='UUID Test Pledge 2',
            slug='uuid-test-pledge-2',
        )
        assert pledge.uuid != pledge2.uuid
        # Test that it's in public_fields
        assert 'enable_community_engagement' in self.plan.features.public_fields


class TestPublicUser:
    """Tests for the PublicUser model."""

    def test_public_user_creation(self):
        """Test that a PublicUser can be created with auto-generated UUID."""
        public_user = PublicUser.objects.create()

        assert public_user.uuid is not None
        assert isinstance(public_user.uuid, uuid.UUID)
        assert public_user.user_data == {}

    def test_public_user_with_user_data(self):
        """Test that a PublicUser can store freeform user data."""
        user_data = {'zip_code': '12345', 'city': 'Test City'}
        public_user = PublicUser.objects.create(user_data=user_data)

        assert public_user.user_data == user_data

    def test_public_user_uuid_unique(self):
        """Test that each PublicUser gets a unique UUID."""
        user1 = PublicUser.objects.create()
        user2 = PublicUser.objects.create()

        assert user1.uuid != user2.uuid

    def test_public_user_str(self):
        """Test the string representation of PublicUser."""
        public_user = PublicUser.objects.create()

        assert str(public_user) == str(public_user.uuid)

    def test_public_user_token_defaults_to_none(self):
        """A freshly created PublicUser has no token until they sign up."""
        public_user = PublicUser.objects.create()

        assert public_user.user_token is None

    def test_regenerate_user_token_returns_raw_and_stores_hash(self):
        """regenerate_user_token() returns the raw token and stores only the hash."""
        user1 = PublicUser.objects.create()
        user2 = PublicUser.objects.create()

        token1 = user1.regenerate_user_token()
        token2 = user2.regenerate_user_token()

        assert token1
        assert token2
        assert token1 != token2

        user1.refresh_from_db()
        assert user1.user_token != token1
        assert user1.user_token == hash_user_token(token1)

    def test_regenerate_user_token_rotates_existing_token(self):
        """Calling regenerate_user_token() again replaces the previous hash."""
        public_user = PublicUser.objects.create()
        first_token = public_user.regenerate_user_token()
        first_hash = public_user.user_token

        second_token = public_user.regenerate_user_token()

        assert second_token != first_token
        public_user.refresh_from_db()
        assert public_user.user_token != first_hash
        assert public_user.user_token == hash_user_token(second_token)

    def test_email_is_lowercased_and_trimmed_on_save(self):
        """Saving a PublicUser normalizes the email to trimmed lowercase."""
        public_user = PublicUser.objects.create(email='  Foo@EXAMPLE.com ')

        assert public_user.email == 'foo@example.com'


class TestPublicUserSignInAttempt:
    """Tests for the PublicUserSignInAttempt model."""

    def test_create_for_generates_attempt_with_hashed_pin(self):
        public_user = PublicUser.objects.create(email='a@example.com')

        attempt, raw_pin = PublicUserSignInAttempt.create_for(public_user)

        assert raw_pin.isdigit()
        assert len(raw_pin) == 6
        assert attempt.pin_hash == hash_pin(raw_pin, attempt.pin_salt)
        assert attempt.pin_hash != raw_pin
        assert attempt.attempts == 0

    def test_create_for_replaces_previous_attempt(self):
        public_user = PublicUser.objects.create(email='a@example.com')
        first_attempt, first_pin = PublicUserSignInAttempt.create_for(public_user)

        second_attempt, second_pin = PublicUserSignInAttempt.create_for(public_user)

        assert second_pin != first_pin
        assert second_attempt.pk == first_attempt.pk
        assert PublicUserSignInAttempt.objects.filter(public_user=public_user).count() == 1

    def test_create_for_stores_anon_uuid(self):
        public_user = PublicUser.objects.create(email='a@example.com')
        anon_uuid = uuid.uuid4()

        attempt, _ = PublicUserSignInAttempt.create_for(public_user, anon_uuid=anon_uuid)

        assert attempt.anon_uuid == anon_uuid

    def test_verify_returns_true_for_correct_pin(self):
        public_user = PublicUser.objects.create(email='a@example.com')
        attempt, raw_pin = PublicUserSignInAttempt.create_for(public_user)

        assert attempt.verify(raw_pin) is True

    def test_verify_returns_false_for_wrong_pin(self):
        public_user = PublicUser.objects.create(email='a@example.com')
        attempt, raw_pin = PublicUserSignInAttempt.create_for(public_user)
        wrong = '000000' if raw_pin != '000000' else '111111'

        assert attempt.verify(wrong) is False

    def test_verify_increments_attempts(self):
        public_user = PublicUser.objects.create(email='a@example.com')
        attempt, _ = PublicUserSignInAttempt.create_for(public_user)

        attempt.verify('000000')
        attempt.verify('111111')

        attempt.refresh_from_db()
        assert attempt.attempts == 2

    def test_verify_returns_false_after_attempts_exhausted(self):
        public_user = PublicUser.objects.create(email='a@example.com')
        attempt, raw_pin = PublicUserSignInAttempt.create_for(public_user)
        for _ in range(PIN_MAX_ATTEMPTS):
            attempt.verify('000000')

        assert attempt.verify(raw_pin) is False

    def test_verify_returns_false_for_expired_attempt(self):
        public_user = PublicUser.objects.create(email='a@example.com')
        attempt, raw_pin = PublicUserSignInAttempt.create_for(public_user)
        attempt.expires_at = timezone.now() - timedelta(minutes=1)
        attempt.save(update_fields=['expires_at'])

        assert attempt.verify(raw_pin) is False


class TestSendPinEmail:
    """Tests for the send_pin_email helper."""

    def test_raises_when_user_has_no_email(self):
        public_user = PublicUser.objects.create()

        with pytest.raises(ValueError, match='no email'):
            send_pin_email(public_user, '123456')

    def test_no_plan_sends_plain_text_only(self):
        public_user = PublicUser.objects.create(email='alice@example.com')
        mail.outbox.clear()

        send_pin_email(public_user, '654321')

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert getattr(msg, 'alternatives', []) == []
        assert '654321' in msg.body
        assert msg.to == ['alice@example.com']

    def test_from_header_is_kausal(self):
        public_user = PublicUser.objects.create(email='alice@example.com')
        mail.outbox.clear()

        send_pin_email(public_user, '111111')

        msg = mail.outbox[0]
        assert msg.from_email.startswith('Kausal ')

    def test_with_plan_subject_includes_plan_name(self):
        plan = PlanFactory.create(name='Example Climate Plan')
        public_user = PublicUser.objects.create(email='alice@example.com')
        mail.outbox.clear()

        with patch('actions.public_user_auth.render_mjml_from_template', return_value='<html></html>'):
            send_pin_email(public_user, '222222', plan=plan)

        msg = mail.outbox[0]
        assert 'Example Climate Plan' in msg.subject
        assert '222222' in msg.body

    def test_with_plan_and_base_template_attaches_html(self):
        plan = PlanFactory.create(name='Example Climate Plan')
        BaseTemplate.objects.create(plan=plan, brand_dark_color='#123456')
        plan.refresh_from_db()
        public_user = PublicUser.objects.create(email='alice@example.com')
        mail.outbox.clear()

        with patch('actions.public_user_auth.render_mjml_from_template', return_value='<html>rendered</html>') as rendered:
            send_pin_email(public_user, '333333', plan=plan)

        rendered.assert_called_once()
        msg = mail.outbox[0]
        assert isinstance(msg, EmailMultiAlternatives)
        assert msg.alternatives == [('<html>rendered</html>', 'text/html')]

    def test_uses_translated_plan_name_when_locale_active(self):
        plan = PlanFactory.create(name='English Plan Name')
        plan.name_fi = 'Suomalainen suunnitelma'
        plan.save()
        public_user = PublicUser.objects.create(email='alice@example.com')
        mail.outbox.clear()

        with translation.override('fi'):
            send_pin_email(public_user, '444444', plan=plan)

        msg = mail.outbox[0]
        assert 'Suomalainen suunnitelma' in msg.subject


class TestPledgeCommitment:
    """Tests for the PledgeCommitment model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.pledge = Pledge.objects.create(
            plan=self.plan,
            name='Test Pledge',
            slug='test-pledge',
        )
        self.public_user = PublicUser.objects.create()

    def test_pledge_commitment_creation(self):
        """Test that a PledgeCommitment can be created."""
        commitment = PledgeCommitment.objects.create(
            pledge=self.pledge,
            public_user=self.public_user,
        )

        assert commitment.pledge == self.pledge
        assert commitment.public_user == self.public_user
        assert commitment.created_at is not None

    def test_pledge_commitment_unique_together(self):
        """Test that a user can only commit to a pledge once."""
        from django.db import IntegrityError

        PledgeCommitment.objects.create(
            pledge=self.pledge,
            public_user=self.public_user,
        )

        with pytest.raises(IntegrityError):
            PledgeCommitment.objects.create(
                pledge=self.pledge,
                public_user=self.public_user,
            )

    def test_pledge_commitment_user_can_commit_to_multiple_pledges(self):
        """Test that a user can commit to multiple different pledges."""
        pledge2 = Pledge.objects.create(
            plan=self.plan,
            name='Second Pledge',
            slug='second-pledge',
        )

        commitment1 = PledgeCommitment.objects.create(
            pledge=self.pledge,
            public_user=self.public_user,
        )
        commitment2 = PledgeCommitment.objects.create(
            pledge=pledge2,
            public_user=self.public_user,
        )

        assert commitment1.pledge != commitment2.pledge
        assert self.public_user.commitments.count() == 2

    def test_pledge_commitment_str(self):
        """Test the string representation of PledgeCommitment."""
        commitment = PledgeCommitment.objects.create(
            pledge=self.pledge,
            public_user=self.public_user,
        )

        assert str(self.public_user.uuid) in str(commitment)
        assert self.pledge.name in str(commitment)


class TestPledgeAttributeResolution:
    """Test that locale copies resolve attributes from the primary translation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create(
            primary_language='en',
            other_languages=['fi'],
        )
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def _create_pledge_with_text_attribute(self):
        """Create a primary pledge and attach a text attribute to it."""
        pledge = PledgeFactory.create(plan=self.plan, name='Green commute')

        pledge_ct = ContentType.objects.get_for_model(Pledge)
        plan_ct = ContentType.objects.get_for_model(self.plan)

        attr_type = AttributeTypeModel.objects.create(
            object_content_type=pledge_ct,
            scope_content_type=plan_ct,
            scope_id=self.plan.id,
            identifier='pledge-tip',
            name='Tip',
            format=AttributeTypeModel.AttributeFormat.TEXT,
        )
        AttributeText.objects.create(
            type=attr_type,
            content_type=pledge_ct,
            object_id=pledge.id,
            text='Take the bus',
        )
        return pledge, attr_type

    def test_locale_copy_resolves_text_attribute_from_primary(self):
        """A non-primary locale copy should see the primary pledge's attributes."""
        primary_pledge, attr_type = self._create_pledge_with_text_attribute()
        primary_pledge.ensure_locale_copies()

        fi_locale = Locale.objects.get(language_code='fi')
        fi_pledge = cast('Pledge', primary_pledge.get_translation(fi_locale))
        assert fi_pledge.id != primary_pledge.id

        attrs = list(fi_pledge.text_attributes.all())
        assert len(attrs) == 0, 'Locale copy should not have its own attribute rows'

        from actions.attributes import AttributeType as AttributeTypeWrapper

        wrapper: AttributeTypeWrapper[Any] = AttributeTypeWrapper.from_model_instance(attr_type)
        resolved = list(wrapper.get_attributes(fi_pledge))
        assert len(resolved) == 1
        assert resolved[0].text == 'Take the bus'

    def test_locale_copy_generic_relations_resolve_from_primary(self):
        """
        GenericRelation traversal on a locale copy should resolve from primary.

        The GraphQL resolver iterates ATTRIBUTE_RELATIONS via getattr(root, rel).all()
        rather than going through AttributeType.get_attributes(). This test verifies
        that path also works for locale copies after applying get_attributes_source().
        """
        primary_pledge, _attr_type = self._create_pledge_with_text_attribute()
        primary_pledge.ensure_locale_copies()

        fi_locale = Locale.objects.get(language_code='fi')
        fi_pledge = cast('Pledge', primary_pledge.get_translation(fi_locale))

        source = fi_pledge.get_attributes_source()
        attrs = list(source.text_attributes.all())
        assert len(attrs) == 1
        assert attrs[0].text == 'Take the bus'
