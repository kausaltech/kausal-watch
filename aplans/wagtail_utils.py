from dal import autocomplete, forward as dal_forward
from django import forms
from django.db.models import Model
from typing import Type, TypeVar

from actions.models import Action, CategoryType, Plan
from indicators.models import Indicator


class ModelChoiceFieldWithValueInList(forms.ModelChoiceField):
    """Like ModelMultipleChoiceField, but allow only one value to be chosen."""
    def to_python(self, value):
        result = super().to_python(value)
        if not result:
            return []
        return [result]

    def prepare_value(self, value):
        if (hasattr(value, '__iter__') and
                not isinstance(value, str) and
                not hasattr(value, '_meta')):
            prepare_value = super().prepare_value
            return [prepare_value(v) for v in value]
        return super().prepare_value(value)


M = TypeVar('M', bound=Model)

def _get_category_fields(plan: Plan, model: Type[M], obj: M | None, with_initial: bool = False) -> dict:
    fields = {}
    if model == Action:
        filter_name = 'editable_for_actions'
    elif model == Indicator:
        filter_name = 'editable_for_indicators'
    else:
        raise Exception()

    assert isinstance(obj, (Action | Indicator))

    for cat_type in plan.category_types.filter(**{filter_name: True}):
        qs = cat_type.categories.all()
        if obj and obj.pk and with_initial:
            initial = obj.categories.filter(type=cat_type)
        else:
            initial = None
        field_class = forms.ModelMultipleChoiceField
        if cat_type.select_widget == CategoryType.SelectWidget.SINGLE:
            field_class = ModelChoiceFieldWithValueInList

            widget = autocomplete.ModelSelect2(
                url='category-autocomplete',
                forward=(
                    dal_forward.Const(cat_type.id, 'type'),
                )
            )
        else:
            field_class = forms.ModelMultipleChoiceField
            widget = autocomplete.ModelSelect2Multiple(
                url='category-autocomplete',
                forward=(
                    dal_forward.Const(cat_type.id, 'type'),
                )
            )
        field = field_class(
            qs, label=cat_type.name, initial=initial, required=False, widget=widget
        )
        field.category_type = cat_type
        fields['categories_%s' % cat_type.identifier] = field
    return fields
