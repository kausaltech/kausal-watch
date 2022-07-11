from django import forms
from django.contrib.admin import SimpleListFilter
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import FieldPanel, ObjectList
from wagtail.contrib.modeladmin.helpers import ButtonHelper
from wagtail.contrib.modeladmin.menus import ModelAdminMenuItem
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.contrib.modeladmin.views import IndexView, DeleteView
from wagtailorderable.modeladmin.mixins import OrderableMixin

from .models import Action, AttributeRichText, AttributeType, Category
from actions.chooser import CategoryTypeChooser
from admin_site.wagtail import (
    AplansCreateView, AplansEditView, AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel
)


class AttributeTypeFilter(SimpleListFilter):
    title = _('Object type')
    parameter_name = 'content_type'

    def lookups(self, request, model_admin):
        action_ct_id = ContentType.objects.get(app_label='actions', model='action').id
        category_ct_id = ContentType.objects.get(app_label='actions', model='category').id
        return (
            (action_ct_id, Action._meta.verbose_name),
            (category_ct_id, Category._meta.verbose_name),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(object_content_type_id=self.value())
        return queryset


def _append_content_type_query_parameter(request, url):
    content_type = request.GET.get('content_type')
    if content_type:
        assert '?' not in url
        return f'{url}?content_type={content_type}'
    return url


class ContentTypeQueryParameterMixin:
    @property
    def index_url(self):
        return _append_content_type_query_parameter(self.request, super().index_url)

    @property
    def create_url(self):
        return _append_content_type_query_parameter(self.request, super().create_url)

    @property
    def edit_url(self):
        return _append_content_type_query_parameter(self.request, super().edit_url)

    @property
    def delete_url(self):
        return _append_content_type_query_parameter(self.request, super().delete_url)


class AttributeTypeIndexView(IndexView):
    page_title = _("Attributes")


class AttributeTypeCreateView(ContentTypeQueryParameterMixin, AplansCreateView):
    def get_object_content_type(self):
        object_ct_id = self.request.GET.get('content_type')
        if not object_ct_id:
            return None
        return ContentType.objects.get(pk=int(object_ct_id))

    def get_page_subtitle(self):
        content_type = self.get_object_content_type()
        model_name = content_type.model_class()._meta.verbose_name_plural
        return _("Attribute for %s") % model_name

    def get_instance(self):
        """Create an attribute type instance and set its object content type to the one given in GET or POST data."""
        instance = super().get_instance()
        object_ct = self.get_object_content_type()
        if object_ct is not None and not instance.pk:
            assert not hasattr(instance, 'object_content_type')
            assert not hasattr(instance, 'scope_content_type')
            instance.object_content_type = object_ct
            if (object_ct.app_label, object_ct.model) == ('actions', 'action'):
                scope_ct_model = 'plan'
            elif (object_ct.app_label, object_ct.model) == ('actions', 'category'):
                scope_ct_model = 'categorytype'
            else:
                raise Exception(f"Invalid content type {object_ct.app_label}.{object_ct.model}")
            instance.scope_content_type = ContentType.objects.get(app_label='actions', model=scope_ct_model)

        # If the instance is plan-specific, set plan to the active one just like we do in AplansCreateView for
        # PlanRelatedModel instances. AttributeType cannot be a PlanRelatedModel because not all attribute types are
        # plan-related.
        if instance.scope_content_type.model == 'plan' and not instance.pk:
            instance.scope_id = self.request.user.get_active_admin_plan().pk

        return instance


class AttributeTypeEditView(ContentTypeQueryParameterMixin, AplansEditView):
    pass


class AttributeTypeDeleteView(ContentTypeQueryParameterMixin, DeleteView):
    pass


class AttributeTypeAdminButtonHelper(ButtonHelper):
    # TODO: duplicated as CategoryAdminButtonHelper
    def add_button(self, *args, **kwargs):
        """
        Only show "add" button if the request contains a content type.

        Set GET parameter content_type to the type for the URL when clicking the button.
        """
        if 'content_type' in self.request.GET:
            data = super().add_button(*args, **kwargs)
            data['url'] = _append_content_type_query_parameter(self.request, data['url'])
            return data
        return None

    def inspect_button(self, *args, **kwargs):
        data = super().inspect_button(*args, **kwargs)
        data['url'] = _append_content_type_query_parameter(self.request, data['url'])
        return data

    def edit_button(self, *args, **kwargs):
        data = super().edit_button(*args, **kwargs)
        data['url'] = _append_content_type_query_parameter(self.request, data['url'])
        return data

    def delete_button(self, *args, **kwargs):
        data = super().delete_button(*args, **kwargs)
        data['url'] = _append_content_type_query_parameter(self.request, data['url'])
        return data


class AttributeTypeAdminMenuItem(ModelAdminMenuItem):
    def is_shown(self, request):
        # Hide it because we will have menu items for listing attribute types of specific content types.
        # Note that we need to register AttributeTypeAdmin nonetheless, otherwise the URLs wouldn't be set up.
        return False


@modeladmin_register
class AttributeTypeAdmin(OrderableMixin, AplansModelAdmin):
    model = AttributeType
    menu_icon = 'tag'
    menu_label = _("Attributes")
    menu_order = 1200
    list_display = ('name', 'format')
    list_filter = (AttributeTypeFilter,)

    basic_panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('format'),
        FieldPanel('unit'),
        CondensedInlinePanel('choice_options', panels=[
            FieldPanel('name'),
            FieldPanel('identifier'),
        ])
    ]

    index_view_class = AttributeTypeIndexView
    create_view_class = AttributeTypeCreateView
    edit_view_class = AttributeTypeEditView
    delete_view_class = AttributeTypeDeleteView
    button_helper_class = AttributeTypeAdminButtonHelper

    def get_edit_handler(self, instance, request):
        basic_panels = list(self.basic_panels)
        # user = request.user
        # plan = user.get_active_admin_plan()
        if instance.object_content_type_id is None:
            content_type_id = request.GET['content_type']
        else:
            content_type_id = instance.object_content_type_id
        content_type = ContentType.objects.get(pk=content_type_id)

        if (content_type.app_label, content_type.model) == ('actions', 'action'):
            # This attribute types has scope 'plan' and we automatically set the scope in AttributeTypeCreateView, so we
            # don't add a panel for choosing a plan.
            pass
        elif (content_type.app_label, content_type.model) == ('actions', 'category'):
            basic_panels.insert(0, FieldPanel('scope_id', widget=CategoryTypeChooser, heading=_("Category type")))
        else:
            raise Exception(f"Invalid content type {content_type.app_label}.{content_type.model}")

        tabs = [ObjectList(basic_panels, heading=_('General'))]

        handler = AplansTabbedInterface(tabs)
        # handler.base_form_class = ModelForm
        return handler

    def get_menu_item(self, order=None):
        return AttributeTypeAdminMenuItem(self, order or self.get_menu_order())

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        action_ct = ContentType.objects.get(app_label='actions', model='action')
        category_ct = ContentType.objects.get(app_label='actions', model='category')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        category_type_ct = ContentType.objects.get(app_label='actions', model='categorytype')
        category_types_in_plan = plan.category_types.all()
        return qs.filter(
            # Attribute types for actions of the active plan
            (Q(object_content_type=action_ct) & Q(scope_content_type=plan_ct) & Q(scope_id=plan.id))
            # Attribute types for categories whose category type is the active plan
            | (Q(object_content_type=category_ct) & Q(scope_content_type=category_type_ct)
               & Q(scope_id__in=category_types_in_plan))
        )


def get_attribute_fields(attribute_types, obj, with_initial=False):
    # Return list containing pairs (attribute_type, fields), where fields is a dict mapping a form field name to a pair
    # (field, model_field_name)
    result = []

    if not obj or not obj.pk:
        with_initial = False

    content_type = ContentType.objects.get_for_model(obj)
    for attribute_type in attribute_types:
        if attribute_type.format == AttributeType.AttributeFormat.ORDERED_CHOICE:
            initial_choice = None
            qs = attribute_type.choice_options.all()
            if with_initial:
                c = (attribute_type.choice_attributes
                     .filter(content_type=content_type, object_id=obj.id)
                     .first())
                if c:
                    initial_choice = c.choice
            field = forms.ModelChoiceField(
                qs, label=attribute_type.name, initial=initial_choice, required=False,
            )
            form_field_name = f'attribute_type_{attribute_type.identifier}'
            result.append((attribute_type, {form_field_name: (field, 'choice')}))
        elif attribute_type.format == AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            initial_choice = None
            initial_text = None
            qs = attribute_type.choice_options.all()
            if with_initial:
                cwt = (attribute_type.choice_with_text_attributes
                       .filter(content_type=content_type, object_id=obj.id)
                       .first())
                if cwt:
                    initial_choice = cwt.choice
                    initial_text = cwt.text
            choice_field = forms.ModelChoiceField(
                qs, label=attribute_type.name, initial=initial_choice, required=False,
            )
            choice_form_field_name = f'attribute_type_{attribute_type.identifier}_choice'
            text_field = AttributeRichText._meta.get_field('text').formfield(
                initial=initial_text, required=False
            )
            text_field.panel_heading = attribute_type.name
            text_form_field_name = f'attribute_type_{attribute_type.identifier}_text'
            result.append((attribute_type, {choice_form_field_name: (choice_field, 'choice'),
                                            text_form_field_name: (text_field, 'text')}))
        elif attribute_type.format == AttributeType.AttributeFormat.RICH_TEXT:
            initial_text = None
            if with_initial:
                val_obj = (attribute_type.rich_text_attributes
                           .filter(content_type=content_type, object_id=obj.id)
                           .first())
                if val_obj is not None:
                    initial_text = val_obj.text

            field = AttributeRichText._meta.get_field('text').formfield(
                initial=initial_text, required=False
            )
            form_field_name = f'attribute_type_{attribute_type.identifier}'
            result.append((attribute_type, {form_field_name: (field, 'text')}))
        elif attribute_type.format == AttributeType.AttributeFormat.NUMERIC:
            initial_value = None
            if with_initial:
                val_obj = (attribute_type.numeric_value_attributes
                           .filter(content_type=content_type, object_id=obj.id)
                           .first())
                if val_obj is not None:
                    initial_value = val_obj.value
            field = forms.FloatField(
                label=attribute_type.name, initial=initial_value, required=False,
            )
            form_field_name = f'attribute_type_{attribute_type.identifier}'
            result.append((attribute_type, {form_field_name: (field, 'value')}))
        else:
            raise Exception('Unsupported attribute type format: %s' % attribute_type.format)
    return result
