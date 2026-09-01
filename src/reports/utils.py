from __future__ import annotations

import typing
from datetime import date, datetime
from typing import Any

if typing.TYPE_CHECKING:
    from typing import Literal

    from django.db.models import Model

    from .types import AttributePath, SerializedAttributeVersion, SerializedVersion


def get_attribute_for_type_from_related_objects(
    required_content_type_id: int,
    action_id: int,
    attribute_type_id: int,
    attribute_versions: dict[AttributePath, SerializedAttributeVersion],
) -> SerializedAttributeVersion | None:
    required_attribute_path: AttributePath = (
        required_content_type_id,
        action_id,
        attribute_type_id,
    )
    return attribute_versions.get(required_attribute_path)


def get_related_model_instances_for_action(
    # TODO: this is used in formatters -- see if it needs to be refactored
    match_criterion: tuple[str, Any] | None,
    related_objects: dict[str, list[SerializedVersion]],
    desired_model: type[Model] | Literal['self'] | Any | None,
):
    match_key = None
    match_value = None
    if match_criterion is not None:
        match_key, match_value = match_criterion
    if desired_model in (None, 'self') or not isinstance(desired_model, type):
        return []
    model_full_path = f'{desired_model.__module__}.{desired_model.__name__}'
    objects = related_objects.get(model_full_path)
    if objects is None:
        return []
    return [x for x in objects if match_criterion is None or match_value == int(x.data[match_key])]


def group_by_model(serialized_versions: list[SerializedVersion]) -> dict[str, list[SerializedVersion]]:
    result: dict[str, list[SerializedVersion]] = {}
    for version in serialized_versions:
        _cls = version.type
        key = f'{_cls.__module__}.{_cls.__name__}'
        result.setdefault(key, [])
        result[key].append(version)
    return result


type ReportCellValue = str | datetime | date | float | None


def get_field_unique_key(field: Any) -> str:
    """
    Generate a unique key for a report field to detect duplicates.

    Different field types need different strategies:
    - attribute fields: use the attribute type's identifier
    - categories fields: use the category type's id
    - other fields: use the block name (they're typically singletons)
    """
    block_name = field.block.name
    # Attribute fields use block name 'attribute' and have an attribute_type in their value
    if block_name == 'attribute' and field.value.get('attribute_type'):
        return f'{block_name}.{field.value["attribute_type"].identifier}'
    if block_name == 'categories' and field.value.get('category_type'):
        category_type = field.value['category_type']
        level = field.value.get('category_level')
        key = f'{block_name}.{category_type.id}'
        if level:
            key = f'{key}.level_{level.id}'
        return key
    return block_name


# These are magic numbers referring to the Excel built-in, non-custom,
# and locale-independent formats for date with or without time. It is used to make
# Excel always display the column in the active locale of the user.
# https://xlsxwriter.readthedocs.io/format.html#format-set-num-format
EXCEL_BUILTIN_NUMBER_FORMAT_FOR_DATES_WHICH_ADAPTS_TO_USER_LOCALE = 14
EXCEL_BUILTIN_NUMBER_FORMAT_FOR_DATETIMES_WHICH_ADAPTS_TO_USER_LOCALE = 22
