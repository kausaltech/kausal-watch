from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, ClassVar

import reversion
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from modeltrans.manager import MultilingualQuerySet
from wagtail import blocks
from wagtail.fields import RichTextField, StreamField
from wagtail.search import index

from kausal_common.models.types import FK, M2M, MLModelManager

from aplans.utils import PlanRelatedOrderedModel

from pages.blocks import LargeImageBlock, QuestionAnswerBlock

from .attributes import ModelWithAttributes
from .plan import Plan

if TYPE_CHECKING:
    from typing import Any

    from modelcluster.fields import PK
    from wagtail.fields import StreamValue

    from kausal_common.users import UserOrAnon

    from actions.attributes import AttributeFieldPanel, AttributeType
    from actions.models.action import Action


class PledgeQuerySet(MultilingualQuerySet['Pledge']):
    def visible_for_user(self, user: UserOrAnon, plan: Plan):
        """Filter pledges visible to the given user for the given plan."""
        qs = self.filter(plan=plan)
        # For now, all pledges in a plan are visible to all users
        # In the future, we may add visibility restrictions
        return qs

    def for_plan(self, plan: Plan):
        """Filter by plan."""
        return self.filter(plan=plan)


@reversion.register(follow=['pledge_action_through'] + ModelWithAttributes.REVERSION_FOLLOW)
class Pledge(
    PlanRelatedOrderedModel,
    ModelWithAttributes,
    ClusterableModel,
    index.Indexed,
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
        help_text=_('A unique identifier for this pledge, used in URLs'),
    )
    description = models.TextField(
        max_length=300,
        blank=True,
        verbose_name=_('description'),
        help_text=_('A short description of the pledge'),
    )
    image: FK[None] = models.ForeignKey(
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
        max_length=120,
        blank=True,
        verbose_name=_('environmental impact at scale'),
        help_text=_(
            'Describe the total environmental benefit if this many residents commit. '
            'Include specific numbers and units. Start with "We save" or "We reduce" for consistency. '
            'Example: "We save <b>9,200kg CO₂e</b> each year"'
        ),
    )
    local_equivalency = RichTextField(
        max_length=120,
        blank=True,
        verbose_name=_('local equivalency comparison'),
        help_text=_(
            'Translate the environmental impact into something relatable and specific to your community. '
            'Use local landmarks, familiar distances, or everyday activities. '
            'Start with "That\'s equivalent to" or "That\'s like" for consistency. '
            'Example: "That\'s equivalent to avoiding <b>575 round trips</b> between City Hall and the waterfront"'
        ),
    )

    # Relationships
    actions: M2M[Action, PledgeActionThrough] = ParentalManyToManyField(
        'actions.Action',
        through='PledgeActionThrough',
        blank=True,
        verbose_name=_('actions'),
        help_text=_('Actions this pledge supports'),
    )

    # Translation configuration
    i18n = TranslationField(
        fields=('name', 'description', 'impact_statement', 'local_equivalency'),
        default_language_field='plan__primary_language_lowercase',
    )

    # Manager configuration
    if TYPE_CHECKING:

        class PledgeManager(MLModelManager['Pledge', PledgeQuerySet]): ...
    else:
        PledgeManager = MLModelManager.from_queryset(PledgeQuerySet)

    objects: ClassVar[PledgeManager] = PledgeManager()

    # Search configuration
    search_fields = [
        index.SearchField('name', boost=10),
        index.SearchField('description'),
        index.SearchField('body'),
    ]

    class Meta:
        db_table = 'actions_pledge'
        verbose_name = _('pledge')
        verbose_name_plural = _('pledges')
        unique_together = [('plan', 'slug')]
        ordering = ['plan', 'order']

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_attribute_types_for_plan(
        cls, plan: Plan, only_in_reporting_tab: bool = False, unless_in_reporting_tab: bool = False  # noqa: ARG003
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


@reversion.register()
class PledgeActionThrough(models.Model):
    """Through model for Pledge-Action many-to-many relationship."""

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
        db_table = 'actions_pledge_actions'
        unique_together = [('pledge', 'action')]
        verbose_name = _('pledge action')
        verbose_name_plural = _('pledge actions')

    def __str__(self) -> str:
        return f'{self.pledge} - {self.action}'
