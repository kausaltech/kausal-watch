"""
Registry of the built-in model fields that a `BuiltInFieldCustomization` may target.

Apps register their own models at import time of their admin modules, so the contents of this
registry depend on which of those modules have been imported. Wagtail's hook discovery loads them
all during startup, well before any admin request, so in practice the registry is complete by the
time it is read. Code that reads it outside the request cycle (a management command, say) must make
sure the relevant admin modules are imported first, or every choice will be rejected as invalid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db.models import Case, Field, Model, When
from django.utils.text import capfirst

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from django.db.models import QuerySet
    from wagtail.admin.panels import Panel

# Keyed by `<app_label>.<model_name>`; populated by `register_customizable_fields()`.
_field_names_by_model_key: dict[str, list[str]] = {}
_models_by_key: dict[str, type[Model]] = {}

# Separator between the model key and the field name in the values offered by `get_field_choices()`.
FIELD_CHOICE_SEPARATOR = ':'


def _model_key(model: type[Model]) -> str:
    return f'{model._meta.app_label}.{model._meta.model_name}'


def humanize_field_name(field_name: str) -> str:
    """Return a display label for `field_name` for cases where no `verbose_name` is available."""
    return capfirst(field_name.replace('_', ' '))


def get_model_label(model: type[Model]) -> str:
    """Return the human-readable label of `model`, as shown in the field and filter widgets."""
    return capfirst(str(model._meta.verbose_name))


def get_content_type_label(content_type: ContentType) -> str:
    """
    Return the human-readable label of `content_type`'s model.

    Falls back to the content type's own string when the model no longer exists, which happens when
    an app or model is removed without running `remove_stale_contenttypes`. A customization left
    pointing at such a row must stay displayable so that it can be found and deleted.
    """
    model = content_type.model_class()
    return get_model_label(model) if model is not None else str(content_type)


def get_field_label(model: type[Model], field_name: str) -> str:
    """
    Return the human-readable label of `field_name` in `model`.

    Most `verbose_name`s follow the Django convention of being lower case and being capitalized when
    rendered, but a handful are capitalized in the model instead. Capitalizing here keeps the labels
    consistent with each other, and with the headings that Wagtail's `FieldPanel` renders for the
    very same fields, which it capitalizes the same way.

    Fields that have no `verbose_name` -- reverse relations (`ForeignObjectRel`) and generic foreign
    keys -- fall back to a humanized version of the field name. So does a field that does not exist
    in `model` (any more), because a customization left behind by a renamed or removed field must
    still be displayable in the admin UI so it can be fixed or deleted.
    """
    try:
        field = model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return humanize_field_name(field_name)
    if isinstance(field, Field):
        return capfirst(str(field.verbose_name))
    return humanize_field_name(field_name)


def field_exists(model: type[Model], field_name: str) -> bool:
    """Return whether `model` still has a field called `field_name`."""
    try:
        model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return False
    return True


def register_customizable_fields(model: type[Model], field_names: Iterable[str]) -> None:
    """
    Declare which built-in fields of `model` may be customized with a `BuiltInFieldCustomization`.

    Call this at import time from the admin module that defines the model's panels, so the
    declaration stays next to the panels it mirrors. Registering the same model repeatedly extends
    the existing declaration instead of replacing it.

    Field names are validated eagerly, so a field that was renamed or removed fails at startup
    rather than silently disappearing from the admin UI. Validation happens before anything is
    recorded, so a rejected call leaves the registry untouched.
    """
    key = _model_key(model)
    names = list(field_names)
    for field_name in names:
        if not field_exists(model, field_name):
            msg = f"'{field_name}' is not a valid field in the model '{key}'"
            raise ImproperlyConfigured(msg)

    registered = _field_names_by_model_key.setdefault(key, [])
    _models_by_key[key] = model
    for field_name in names:
        if field_name not in registered:
            registered.append(field_name)


def collect_customizable_field_names(panels: Iterable[Panel[Any, Any]]) -> list[str]:
    """
    Collect the field names of all customizable built-in field panels in `panels`, recursively.

    Use this to derive a registration from statically declared panel sequences. Panels that are
    built per request cannot be discovered this way and have to be registered explicitly.
    """
    from admin_site.wagtail import CustomizableBuiltInFieldPanel, CustomizableBuiltInPlanFilteredFieldPanel

    customizable_panel_classes = (CustomizableBuiltInFieldPanel, CustomizableBuiltInPlanFilteredFieldPanel)
    field_names: list[str] = []
    for panel in panels:
        if isinstance(panel, customizable_panel_classes):
            if panel.field_name not in field_names:
                field_names.append(panel.field_name)
            continue
        children: Sequence[Panel[Any, Any]] = getattr(panel, 'children', ())
        for field_name in collect_customizable_field_names(children):
            if field_name not in field_names:
                field_names.append(field_name)
    return field_names


def _verbose_name_key(model: type[Model]) -> str:
    return str(model._meta.verbose_name).lower()


def get_customizable_models() -> list[type[Model]]:
    """Return the registered models, ordered by their verbose name."""
    return sorted(_models_by_key.values(), key=_verbose_name_key)


def get_customizable_field_names(model: type[Model]) -> list[str]:
    """Return the registered field names of `model`, in registration order."""
    return list(_field_names_by_model_key.get(_model_key(model), ()))


def get_customizable_content_types() -> QuerySet[ContentType]:
    """
    Return the content types of all registered models, ordered like `get_customizable_models()`.

    `ContentType` has no default ordering, so without the explicit `Case` the caller would get
    whatever order the database happens to return rather than the verbose-name order.
    """
    pks = [ContentType.objects.get_for_model(model).pk for model in get_customizable_models()]
    ordering = Case(*[When(pk=pk, then=position) for position, pk in enumerate(pks)])
    return ContentType.objects.filter(pk__in=pks).order_by(ordering)


def is_customizable_field(model: type[Model], field_name: str) -> bool:
    return field_name in _field_names_by_model_key.get(_model_key(model), ())


def make_field_choice_value(model: type[Model], field_name: str) -> str:
    return f'{_model_key(model)}{FIELD_CHOICE_SEPARATOR}{field_name}'


def parse_field_choice_value(value: str) -> tuple[type[Model], str] | None:
    """Resolve a value produced by `make_field_choice_value()` back to a model and a field name."""
    model_key, separator, field_name = value.partition(FIELD_CHOICE_SEPARATOR)
    if not separator:
        return None
    model = _models_by_key.get(model_key)
    if model is None or not is_customizable_field(model, field_name):
        return None
    return (model, field_name)


def get_field_choices(
    extra_choices: Mapping[type[Model], Sequence[tuple[str, str]]] | None = None,
) -> list[tuple[str, list[tuple[str, str]]]]:
    """
    Return the customizable fields of all registered models as choices grouped by model.

    Grouping into optgroups lets the user pick the model and the field in a single widget, which
    avoids a choice of field that does not exist in the chosen model.

    `extra_choices` adds ready-made options to the group of the model they belong to, adding a group
    for a model that is not registered at all. Callers use this to keep an option selectable that
    the registry does not offer; putting the merge here rather than in the caller keeps every model
    to a single group and preserves the verbose-name ordering.
    """
    extra = dict(extra_choices or {})
    models = get_customizable_models()
    models.extend(model for model in extra if model not in models)
    models.sort(key=_verbose_name_key)

    groups: list[tuple[str, list[tuple[str, str]]]] = []
    for model in models:
        choices = [
            (make_field_choice_value(model, field_name), get_field_label(model, field_name))
            for field_name in get_customizable_field_names(model)
        ]
        choices.extend(extra.get(model, ()))
        if choices:
            groups.append((get_model_label(model), choices))
    return groups
