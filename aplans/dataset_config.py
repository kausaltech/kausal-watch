"""
Configure the kausal_common.datasets app.

There is some project-specific configration required for the reusable datasets apps
found in kausal_common.datasets to make it adapt to different use cases in Watch
and Paths. The configuration must be found in the module
dataset_config under the project directory.
"""

from __future__ import annotations

import typing

from django.utils.translation import gettext_lazy as _

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model

    import pint

    from aplans.types import WatchAdminRequest


def schema_default_scope():
    # Only call in view contexts where the context has been initialized
    from aplans.context_vars import ctx_request

    request = typing.cast('WatchAdminRequest', ctx_request.get())
    return request.get_active_admin_plan()

_ureg: pint.UnitRegistry | None = None

def _get_unit_registry() -> pint.UnitRegistry:
    global _ureg  # noqa: PLW0603
    if _ureg is not None:
        return _ureg
    import pint
    ureg = pint.UnitRegistry()
    # Register domain-specific units common in climate action plans
    ureg.define('CO2e = [] = CO2_equivalent')
    ureg.define('tCO2e = metric_ton * CO2e')
    ureg.define('tCO2 = metric_ton * CO2e')
    ureg.define('ktCO2e = 1000 * tCO2e')
    ureg.define('EUR = [] = euro')
    ureg.define('USD = [] = dollar')
    _ureg = ureg
    return _ureg

def validate_unit(unit: str) -> None:
    """
    Raise `ValidationError` if `unit` is not a recognized pint unit.

    Empty/blank units are allowed (some metrics are dimensionless counts).
    """
    if not unit or not unit.strip():
        return

    from tokenize import TokenError

    from django.core.exceptions import ValidationError

    import pint

    ureg = _get_unit_registry()
    try:
        ureg.parse_expression(unit)
    except pint.UndefinedUnitError as err:
        raise ValidationError(
            _('Unknown unit "%(unit)s". Please use a valid unit (e.g., kg, tCO2e, MWh, EUR).'),
            params={'unit': unit},
            code='invalid_unit',
        ) from err
    except (pint.errors.DefinitionSyntaxError, AssertionError, TokenError) as err:
        raise ValidationError(
            _('Invalid unit syntax "%(unit)s".'),
            params={'unit': unit},
            code='invalid_unit_syntax',
        ) from err


DATA_SOURCE_DEFAULT_SCOPE_CONTENT_TYPE = ('actions', 'plan')
SCHEMA_HAS_SINGLE_DATASET: bool = False
SCHEMA_DEFAULT_SCOPE_FUNCTION: Callable[[], Model] | None = schema_default_scope
# Permission policies for datasets
SHOW_DATASETS_IN_MENU: bool = False
SHOW_SCHEMAS_IN_MENU: bool = False
SCHEMA_PERMISSION_POLICY = 'datasets.permission_policy.DatasetSchemaPermissionPolicy'
DATASET_PERMISSION_POLICY = 'datasets.permission_policy.ScopeInheritedDatasetPermissionPolicy'
DATA_POINT_PERMISSION_POLICY = 'datasets.permission_policy.DataPointPermissionPolicy'
DATA_SOURCE_PERMISSION_POLICY = 'datasets.permission_policy.DataSourcePermissionPolicy'
