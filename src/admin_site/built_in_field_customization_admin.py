from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.forms import ModelChoiceField
from django.utils.translation import gettext_lazy as _
from wagtail.admin.filters import WagtailFilterSet
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, ObjectList
from wagtail.admin.ui.tables import Column
from wagtail.snippets.models import register_snippet

from django_filters import filters

from kausal_common.users import user_or_bust

from admin_site.field_customization import (
    field_exists,
    get_content_type_label,
    get_customizable_content_types,
    get_field_choices,
    get_field_label,
    is_customizable_field,
    make_field_choice_value,
    parse_field_choice_value,
)
from admin_site.forms import WatchAdminModelForm
from admin_site.models import BuiltInFieldCustomization
from admin_site.permissions import PlanAdminOnlyPermissionPolicy
from admin_site.viewsets import WatchViewSet

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet
    from django.http import HttpRequest


class BuiltInFieldCustomizationForm(WatchAdminModelForm[BuiltInFieldCustomization]):
    """
    Form for customizing a built-in field of a model such as `Action`.

    The customized field is chosen with a single `field` widget whose options are grouped by model,
    rather than with separate `content_type` and `field_name` widgets. That way the user cannot pick
    a field that does not exist in the chosen model, and we avoid a dependent dropdown. The two
    underlying model fields are derived from the choice in `clean()`.
    """

    field = forms.ChoiceField(
        label=_('Field'),
        help_text=_('The built-in field whose appearance and access rights are customized'),
    )

    _selected_field: tuple[type[Model], str] | None = None

    class Meta:
        model = BuiltInFieldCustomization
        fields = ('label_override', 'help_text_override', 'instances_visible_for', 'instances_editable_by')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_choice = self.fields['field']
        assert isinstance(field_choice, forms.ChoiceField)
        current = self._get_current_field()
        field_choice.choices = self._build_choices(current)
        self.initial.setdefault('field', make_field_choice_value(*current) if current else None)

    def _get_current_field(self) -> tuple[type[Model], str] | None:
        """
        Return the model and field this customization currently points at, if it still resolves.

        Returns None for a field that no longer exists in the model, so that the widget opens unset
        and the user has to re-point the customization at a valid field (or delete it).
        """
        instance = self.instance
        if instance.pk is None:
            # A persisted row always has a content type; the column is not nullable.
            return None
        model = instance.content_type.model_class()
        if model is None or not field_exists(model, instance.field_name):
            return None
        return (model, instance.field_name)

    @staticmethod
    def _build_choices(current: tuple[type[Model], str] | None) -> list[tuple[str, list[tuple[str, str]]]]:
        """
        Return the registered choices, plus the current field if it is not among them.

        A customization may point at a field that exists but was never registered -- one created in
        the REPL, or one whose panel has since been removed. Offering it keeps the customization
        editable instead of forcing the user to re-point it just to change its label. The extra
        option is handed to `get_field_choices()` rather than appended here, so that it lands in its
        model's existing group instead of a second group with the same name.
        """
        if current is None or is_customizable_field(*current):
            return get_field_choices()
        model, field_name = current
        label = _('%(field)s (no longer customizable)') % {'field': get_field_label(model, field_name)}
        return get_field_choices({model: [(make_field_choice_value(model, field_name), label)]})

    def clean_field(self) -> str:
        value = self.cleaned_data['field']
        selected = parse_field_choice_value(value)
        if selected is None:
            # The widget also offers the customization's own field when it is no longer registered.
            current = self._get_current_field()
            if current is not None and value == make_field_choice_value(*current):
                selected = current
        if selected is None:
            raise ValidationError(_('This field cannot be customized.'))
        self._selected_field = selected
        return value

    def clean(self) -> dict[str, Any] | None:
        cleaned_data = super().clean()
        if self._selected_field is None:
            return cleaned_data
        model, field_name = self._selected_field
        self.instance.content_type = ContentType.objects.get_for_model(model)
        self.instance.field_name = field_name
        self._validate_uniqueness()
        return cleaned_data

    # `content_type` and `field_name` are derived from `field` and are not form fields of their own,
    # so model-level validation errors reported for them would otherwise raise a ValueError.
    _DERIVED_ERROR_FIELDS = ('content_type', 'field_name')

    @classmethod
    def _remap_error_field[T: (str, str | None)](cls, field: T) -> T:
        return 'field' if field in cls._DERIVED_ERROR_FIELDS else field

    def add_error(self, field: str | None, error: Any) -> None:
        if isinstance(error, ValidationError) and hasattr(error, 'error_dict'):
            error = ValidationError({self._remap_error_field(name): errors for name, errors in error.error_dict.items()})
        else:
            field = self._remap_error_field(field)
        super().add_error(field, error)

    def _validate_uniqueness(self) -> None:
        """
        Reject a second customization for the same field in the same plan.

        The model has a unique constraint for this, but `plan` is not part of the form, so Django
        skips validating the constraint and we would hit an IntegrityError instead of a form error.
        """
        # Both view classes always pass the active plan; failing loudly beats falling back to no
        # uniqueness check at all, since that would surface as an IntegrityError 500.
        assert self.plan is not None
        duplicates = BuiltInFieldCustomization.objects.filter(
            plan=self.plan,
            content_type=self.instance.content_type,
            field_name=self.instance.field_name,
        )
        if self.instance.pk is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            self.add_error('field', _('This field is already customized in this plan.'))


def customizable_content_types_for_request(_request: HttpRequest | None) -> QuerySet[ContentType]:
    """Provide the filter's options lazily, so the content type lookup stays out of import time."""
    return get_customizable_content_types()


class CustomizableContentTypeChoiceField(ModelChoiceField[ContentType]):
    def label_from_instance(self, obj: ContentType) -> str:
        return get_content_type_label(obj)


class CustomizableContentTypeFilter(filters.ModelChoiceFilter):
    # The stub declares this as an unparameterized `type[ModelChoiceField]`, which `type[]`
    # invariance makes incompatible with our parameterized subclass.
    field_class: type[ModelChoiceField[Any]] = CustomizableContentTypeChoiceField


class BuiltInFieldCustomizationFilterSet(WagtailFilterSet):
    content_type = CustomizableContentTypeFilter(
        # Without an explicit queryset this offers every content type in the installation, of which
        # only the handful of registered ones can ever appear here. django-filter accepts a callable
        # and calls it per request; the type stub only admits a QuerySet, hence the ignore.
        queryset=customizable_content_types_for_request,  # pyright: ignore[reportArgumentType]
        label=_('Model'),
    )

    class Meta:
        model = BuiltInFieldCustomization
        fields = ['content_type']


class BuiltInFieldCustomizationViewSet(WatchViewSet[BuiltInFieldCustomization, BuiltInFieldCustomizationForm]):
    """Admin interface for customizing built-in fields of the active plan."""

    model = BuiltInFieldCustomization
    icon = 'form'
    menu_label = _('Field customizations')
    # The attribute type items ("Fields (Action)" and friends) are appended by
    # `add_attribute_types_to_settings_menu()` with the default order of 1000, and category types
    # follow at 1100, so this sits between the two.
    menu_order = 1001
    add_to_settings_menu = True
    # `field_label` comes first, and as a plain name rather than a `Column`, because Wagtail turns
    # only the first such entry into the title column: the one linking to the edit view and carrying
    # the row's buttons. A `Column` instance in that position is used verbatim, leaving the listing
    # with no way to open a row.
    #
    # The model is shown through `content_type_label` rather than the content type itself, whose
    # `__str__` renders "Actions | action" -- a second spelling of what the filter shows as "Action".
    # `sort_key` keeps the column sortable by the underlying foreign key.
    #
    # `field_name` is shown besides the label because the label is computed and cannot be searched
    # in the ORM; showing the raw name makes the term that `search_fields` does match discoverable.
    list_display = [
        'field_label',
        Column('content_type_label', label=_('Model'), sort_key='content_type'),
        'field_name',
        'instances_visible_for',
        'instances_editable_by',
    ]
    filterset_class = BuiltInFieldCustomizationFilterSet
    search_fields = ['field_name', 'label_override', 'help_text_override']

    panels = [
        FieldPanel('field'),
        MultiFieldPanel(
            [
                FieldPanel('label_override'),
                FieldPanel('help_text_override'),
            ],
            heading=_('Appearance'),
            help_text=_(
                'Leave empty to use the label and help text that the field has by default. These have no effect on '
                'fields that are shown in a tab or panel of their own, such as tasks.'
            ),
        ),
        MultiFieldPanel(
            [
                FieldPanel('instances_visible_for'),
                FieldPanel('instances_editable_by'),
            ],
            heading=_('Access rights'),
        ),
    ]

    @property
    def permission_policy(self):
        return PlanAdminOnlyPermissionPolicy(self.model)

    def get_edit_handler(self):
        return ObjectList(self.panels, base_form_class=BuiltInFieldCustomizationForm).bind_to_model(self.model)

    def get_queryset(self, request: HttpRequest) -> QuerySet[BuiltInFieldCustomization]:
        plan = user_or_bust(request.user).get_active_admin_plan()
        return self.model.objects.filter(plan=plan).select_related('content_type', 'plan')


register_snippet(BuiltInFieldCustomizationViewSet)
