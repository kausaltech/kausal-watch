from __future__ import annotations

import typing

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail.models import Page

from aplans.utils import PlanRelatedModelWithRevision

from actions.models import Action, Plan
from actions.models.category import Category
from pages.models import ActionListPage, CategoryPage


class UserFeedback(PlanRelatedModelWithRevision):
    class FeedbackType(models.TextChoices):
        GENERAL = '', _('General')
        ACCESSIBILITY = 'accessibility', _('Accessibility')
        ACTION = 'action', _('Action')
        CATEGORY = "category", _("Category")

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='user_feedbacks', verbose_name=_("plan"))
    type = models.CharField(
        max_length=30, choices=FeedbackType.choices, verbose_name=_("type"), blank=True,
    )
    action = models.ForeignKey(
        Action, blank=True, null=True, on_delete=models.SET_NULL, related_name='user_feedbacks',
        verbose_name=_("action"),
    )
    category = models.ForeignKey(
        Category, blank=True, null=True, on_delete=models.SET_NULL, related_name='user_feedbacks',
        verbose_name=_("category"),
    )

    name = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("name"))
    email = models.EmailField(null=True, blank=True, verbose_name=_("email address"))
    comment = models.TextField(verbose_name=_("comment"), blank=True)

    url = models.URLField(verbose_name=_("URL"), max_length=500)

    additional_fields = models.JSONField(blank=True, null=True)
    page_id = models.CharField(null=True, blank=True, verbose_name=_("page id"))
    latest_revision = models.ForeignKey(
        "wagtailcore.Revision",
        related_name="+",
        verbose_name=_("latest revision"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    is_processed = models.BooleanField(default=False, verbose_name=_("is processed"))

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='user_feedbacks')

    public_fields: typing.ClassVar = ['id', 'created_at']

    class Meta:
        verbose_name = _('user feedback')
        verbose_name_plural = _('user feedbacks')

    def user_can_change_is_processed(self, user):
        return user.is_general_admin_for_plan(self.plan)

    def __str__(self):
        sender = self.name or self.email
        return f'{sender} ({self.created_at})'

    def clean(self):
        super().clean()
        page_id = self.page_id
        latest_revision = get_latest_revision(page_id)
        self.latest_revision = latest_revision
        comment = self.comment
        additional_fields = self.additional_fields

        if additional_fields and not any(additional_fields.values()):
            additional_fields = None
        if not comment and not additional_fields:
            raise ValidationError(_("At least one field must be filled."))

        self.save()


def get_latest_revision(page_id):
    try:
        page = Page.objects.get(id=page_id)
        if isinstance(page.specific, ActionListPage):
            latest_revision = page.get_latest_revision()
        elif isinstance(page.specific, CategoryPage):
            latest_revision = page.get_parent().get_latest_revision()
        else:
            raise ValidationError("Wrong page.")
        if latest_revision:
            return latest_revision
        raise ValidationError("No revisions found for the specified page.")
    except Page.DoesNotExist as e :
        # We might be at the feedback page or accessibility feedback page
        # where a page doesn't exist and is not needed because it's lacking
        # the block configuration anyway
        return None


# TODO: The validation works but not critical now and not tested enough yet.
#  Might take in to use with better time later.

# def get_blocks_from_revision(revision_page):
#     if isinstance(revision_page, ActionListPage):
#         details_main_top = revision_page.details_main_top
#         details_main_bottom = revision_page.details_main_bottom

#         blocks_top = details_main_top.blocks_by_name("contact_form")
#         blocks_bottom = details_main_bottom.blocks_by_name("contact_form")
#         blocks = blocks_top + blocks_bottom
#     elif isinstance(revision_page, CategoryTypePage):
#         level_layouts = revision_page.level_layouts
#         blocks = []
#         for layout in level_layouts.all():
#             blocks.extend(layout.layout_main_bottom.blocks_by_name("contact_form"))
#     else:
#         return None
#     block_dict = {}
#     for block in blocks:
#         block_dict[block.id] = block.value["fields"].get_prep_value()

#     return block_dict


# def validate_feedback_against_revision(revision_page, feedback_data):
#     block_dict = get_blocks_from_revision(revision_page)
#     if feedback_data:
#         if block_dict is None:
#             raise ValidationError("No contact form blocks found in the specified revision.")

#         for block_id, block_fields in block_dict.items():
#             if block_id not in feedback_data:
#                 raise ValidationError("Missing feedback data for block")
#             block_feedback_data = feedback_data[block_id]
#             validate_feedback_against_block(block_fields, block_feedback_data)
#             return


# def validate_feedback_against_block(block_fields, block_feedback_data):
#     for field in block_fields:
#         field_label = field['value']['field_label']
#         field_type = field['value']['field_type']
#         field_required = field['value']['field_required']

#         if field_label not in block_feedback_data:
#             if field_required:
#                 raise ValidationError("Missing required field: %s " % field_label)
#             continue

#         field_value = block_feedback_data[field_label]

#         if field_type == 'text':
#             if not isinstance(field_value, str):
#                 raise ValidationError("Invalid data type for field: %s. Expected string." % field_label)
#         elif field_type == 'checkbox':
#             if not isinstance(field_value, list):
#                 raise ValidationError("Invalid data type for field: %s. Expected list." % field_label)
#             valid_choices = [choice['value']['choice_value'] for choice in field['value']['choices']]
#             for value in field_value:
#                 if value not in valid_choices:
#                     raise ValidationError("Invalid choice value for field: %s" % field_label)
#         elif field_type == 'dropdown':
#             if not isinstance(field_value, str):
#                 raise ValidationError("Invalid data type for field: %s. Expected string." % field_label)
#             valid_choices = [choice['value']['choice_value'] for choice in field['value']['choices']]

#             if not field_required:
#                 valid_choices.append("")
#             if field_value not in valid_choices:
#                 raise ValidationError("Invalid choice value for field: %s" % field_label)
