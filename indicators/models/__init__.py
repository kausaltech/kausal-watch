from __future__ import annotations

# Computation models
from kausal_common.datasets.models import DatasetMetricComputation

# Action link models
from indicators.models.action_links import (
    ActionIndicator,
    ActionIndicatorManager,
    ActionIndicatorQuerySet,
)

# Common indicator models
from indicators.models.common_indicator import (
    CommonIndicator,
    CommonIndicatorNormalizator,
    FrameworkIndicator,
    PlanCommonIndicator,
    RelatedCommonIndicator,
)

# Contact person models
from indicators.models.contact_persons import (
    IndicatorContactPerson,
)

# Dimension models
from indicators.models.dimensions import (
    CommonIndicatorDimension,
    Dimension,
    DimensionCategory,
    IndicatorDimension,
    PlanDimension,
)

# Goal data point models
from indicators.models.goal_data_point import (
    IndicatorGoalDataPoint,
    IndicatorGoalDimensionCategory,
)

# Main indicator models
from indicators.models.indicator import (
    Indicator,
    IndicatorCategoryThrough,
    IndicatorLevel,
    IndicatorLevelManager,
    IndicatorLevelQuerySet,
    IndicatorManager,
    IndicatorQuerySet,
)

# Import and expose all models for backwards compatibility
# Metadata models
from indicators.models.metadata import (
    Dataset,
    DatasetLicense,
    Framework,
    Quantity,
    Unit,
)

# Relationship models
from indicators.models.relationships import (
    IndicatorRelationship,
    RelatedIndicator,
)

# Value models
from indicators.models.values import (
    IndicatorGoal,
    IndicatorGraph,
    IndicatorValue,
    IndicatorValueCategory,
)

__all__ = [
    'ActionIndicator',
    'ActionIndicatorManager',
    'ActionIndicatorQuerySet',
    'CommonIndicator',
    'CommonIndicatorDimension',
    'CommonIndicatorNormalizator',
    'Dataset',
    'DatasetLicense',
    'DatasetMetricComputation',
    'Dimension',
    'DimensionCategory',
    'Framework',
    'FrameworkIndicator',
    'Indicator',
    'IndicatorCategoryThrough',
    'IndicatorContactPerson',
    'IndicatorDimension',
    'IndicatorGoal',
    'IndicatorGoalDataPoint',
    'IndicatorGoalDimensionCategory',
    'IndicatorGraph',
    'IndicatorLevel',
    'IndicatorLevelManager',
    'IndicatorLevelQuerySet',
    'IndicatorManager',
    'IndicatorQuerySet',
    'IndicatorRelationship',
    'IndicatorValue',
    'IndicatorValueCategory',
    'PlanCommonIndicator',
    'PlanDimension',
    'Quantity',
    'RelatedCommonIndicator',
    'RelatedIndicator',
    'Unit',
]
