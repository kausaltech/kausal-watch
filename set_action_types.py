#!/usr/bin/env python
import django
import json
import os
import pytz
import re
import requests
from collections import Counter
from django.core.files.images import ImageFile
from django.utils import timezone
from datetime import datetime
from io import BytesIO

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aplans.settings')
django.setup()

from django_orghierarchy.models import DataSource, Organization  # noqa
from actions.models import Action, ActionImplementationPhase, ActionLink, ActionResponsibleParty, Category, CategoryIcon, CategoryMetadataNumericValue, CategoryType, CategoryTypeMetadata, Plan  # noqa
from indicators.models import Indicator, IndicatorLevel, IndicatorGoal, IndicatorValue, Unit  # noqa
from images.models import AplansImage  # noqa
from pages.models import CategoryPage  # noqa
from wagtail.core.models import Page  # noqa
from wagtail.core.rich_text import RichText  # noqa

plan = Plan.objects.get(identifier='kpr')

# Create CategoryType whose catogies will be the different types of actions
action_types_category_type_data = {
    'name': "Typ",
    'usable_for_actions': True,
    'hide_category_identifiers': True,
}
action_types_category_type, _ = CategoryType.objects.update_or_create(
    plan=plan,
    identifier='action',
    defaults=action_types_category_type_data,
)

d = json.load(open('published_sv.json'))

nodes = {}
parent_of = {}

actions = {}

for action in d['publishedBoardVersion']['actions'].values():
    id = action['id']
    actions[id] = action

# Create actions
action_for_uuid = {}
for i, action_data in enumerate(actions.values()):
    identifier = str(i+1)
    properties = action_data['actionProperties']

    action = Action.objects.get(plan=plan, identifier=identifier)

    # Set type of action
    action_type = properties.get('actionType')
    if action_type:
        category = Category.objects.get(type=action_types_category_type, identifier=action_type)
        action.categories.add(category)
