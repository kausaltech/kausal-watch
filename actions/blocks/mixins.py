from __future__ import annotations

import contextlib
import typing

from django import forms
from django.apps import apps
from django.utils.translation import gettext as _

if typing.TYPE_CHECKING:
    from wagtail.blocks import BaseStreamBlock
    from wagtail.blocks.stream_block import StreamValue

    from actions.models import AttributeType, CategoryType
    from admin_site.wagtail import AplansAdminModelForm

if typing.TYPE_CHECKING:
    _Base = BaseStreamBlock
else:
    _Base = object

type SupportedModel = AttributeType | CategoryType

class ActionListPageBlockPresenceMixin(_Base):
    """
    Supports adding/removing blocks which represent some model instance.

    Sometimes we want the user to be able to add/remove blocks within some
    stream blocks within the ActionListPage from within the edit form of the model
    instance itself and not only the edit form of the ActionListPage.

    This mixin needs to be added to the stream block of the ActionListPage which
    we want to control in this fashion. ActionListPageBlockFormMixin (see below)
    needs to be added to the instance editing form.
    """

    model_instance_container_blocks: dict[type[SupportedModel], str]

    def _get_block_names(self, instance: SupportedModel) -> tuple[str, str]:
        model_class = type(instance)
        block_name = self.model_instance_container_blocks[model_class]
        child_block = self.child_blocks[block_name]
        sub_block_name = child_block.model_instance_container_blocks[instance._meta.model]
        return (block_name, sub_block_name)

    def contains_model_instance(self, instance: SupportedModel, blocks: StreamValue):
        block_name, sub_block_name = self._get_block_names(instance)
        container_blocks = (child for child in blocks if child.block_type == block_name)
        return any(child.value.get(sub_block_name) == instance for child in container_blocks)

    def insert_model_instance(self, instance: SupportedModel, blocks: StreamValue):
        block_name, sub_block_name = self._get_block_names(instance)
        blocks.append((block_name, {sub_block_name: instance}))

    def remove_model_instance(self, instance: SupportedModel, blocks: StreamValue):
        block_name, sub_block_name = self._get_block_names(instance)
        try:
            i = next(
                i for i, block in enumerate(blocks)
                if (block.block_type == block_name and
                    block.value[sub_block_name] == instance)
            )
        except StopIteration as e:
            msg = f'Model instance {instance} is not referenced in blocks'
            raise ValueError(msg) from e
        else:
            del blocks[i]


if typing.TYPE_CHECKING:
    _FormBase = AplansAdminModelForm
else:
    _FormBase = forms.Form

class ActionListPageBlockFormMixin(_FormBase):
    """
    Implements adding/removing blocks which represent the model instance being edited.

    Sometimes we want the user to be able to add/remove blocks within some
    stream blocks within the ActionListPage from within the edit form of the model
    instance itself and not only the edit form of the ActionListPage.

    This mixin needs to be added to the instance editing form.
    """

    # Choice names are field names in ActionListPage
    ACTION_LIST_FILTER_SECTION_CHOICES = [
        ('', _('[not included]')),
        ('primary_filters', _('in primary filters')),
        ('main_filters', _('in main filters')),
        ('advanced_filters', _('in advanced filters')),
    ]
    ACTION_DETAIL_CONTENT_SECTION_CHOICES = [
        ('', _('[not included]')),
        ('details_main_top', _('in main column (top)')),
        ('details_main_bottom', _('in main column (bottom)')),
        ('details_aside', _('in side column')),
    ]

    action_list_filter_section = forms.ChoiceField(choices=ACTION_LIST_FILTER_SECTION_CHOICES, required=False)
    action_detail_content_section = forms.ChoiceField(choices=ACTION_DETAIL_CONTENT_SECTION_CHOICES, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is not None:
            ActionListPage = apps.get_model('pages', 'ActionListPage')
            action_list_page = self.plan.root_page.get_children().type(ActionListPage).get().specific
            for field_name in (f for f, _ in self.ACTION_LIST_FILTER_SECTION_CHOICES if f):
                if action_list_page.contains_model_instance_block(self.instance, field_name):
                    self.fields['action_list_filter_section'].initial = field_name
                    break
            for field_name in (f for f, _ in self.ACTION_DETAIL_CONTENT_SECTION_CHOICES if f):
                if action_list_page.contains_model_instance_block(self.instance, field_name):
                    self.fields['action_detail_content_section'].initial = field_name
                    break

    def save(self, commit=True):
        instance = super().save(commit)
        ActionListPage = apps.get_model('pages', 'ActionListPage')
        action_list_page = self.plan.root_page.get_children().type(ActionListPage).get().specific
        action_list_filter_section = self.cleaned_data.get('action_list_filter_section')
        for field_name in (f for f, __ in self.ACTION_LIST_FILTER_SECTION_CHOICES if f):
            if action_list_filter_section == field_name:
                if not action_list_page.contains_model_instance_block(instance, field_name):
                    action_list_page.insert_model_instance_block(instance, field_name)
            else:
                with contextlib.suppress(ValueError):  # Don't care if instance wasn't there in the first place
                    action_list_page.remove_model_instance_block(instance, field_name)
        action_detail_content_section = self.cleaned_data.get('action_detail_content_section')
        for field_name in (f for f, __ in self.ACTION_DETAIL_CONTENT_SECTION_CHOICES if f):
            if action_detail_content_section == field_name:
                if not action_list_page.contains_model_instance_block(instance, field_name):
                    action_list_page.insert_model_instance_block(instance, field_name)
            else:
                with contextlib.suppress(ValueError):  # Don't care if instance wasn't there in the first place
                    action_list_page.remove_model_instance_block(instance, field_name)
        action_list_page.save()
        return instance
