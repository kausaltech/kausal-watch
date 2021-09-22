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
from actions.models import Action, ActionImplementationPhase, ActionLink, ActionResponsibleParty, Category, CategoryMetadataNumericValue, CategoryType, CategoryTypeMetadata, Plan  # noqa
from indicators.models import Indicator, IndicatorLevel, IndicatorGoal, IndicatorValue, Unit  # noqa
from images.models import AplansImage  # noqa
from pages.models import CategoryPage  # noqa
from wagtail.core.models import Page  # noqa
from wagtail.core.rich_text import RichText  # noqa

tz = pytz.timezone('Europe/Stockholm')


SECTOR_COLORS = {
    'Transport': '#56C38E',
    'Industri': '#336D94',
    'Jordbruk': '#C88217',
    'Energi': '#F4CE73',
    'Övrigt': '#D46262',
}


def clean_organization_name(name):
    return name.strip()


def str_to_id(v):
    # https://stackoverflow.com/questions/3303312/how-do-i-convert-a-string-to-a-valid-variable-name-in-python
    return re.sub(r'\W|^(?=\d)', '_', v)


def delete_old_data(plan):
    # Not used anymore, but call manually if needed
    Action.objects.filter(plan=plan).delete()
    CategoryPage.objects.filter(category__type__plan=plan).delete()
    Category.objects.filter(type__plan=plan).delete()

    # Delete category pages from previous invocations
    plan.root_page.get_children().filter(title='Categories').delete()

    # Reload plan (and in particular plan.root_page) because otherwise things will be messed up:
    # https://github.com/wagtail/wagtail/issues/3402
    plan.refresh_from_db()


def to_rich_text(text):
    return '\n'.join([f'<p>{line}</p>' for line in text.splitlines() if line])


# Create Organization
org_data = {
    'name': 'Klimatpolitiska rådet',
    'abbreviation': 'KPR',
}
org, _ = Organization.objects.update_or_create(
    id='kpr',  # TBD: All other ids contain a colon
    defaults=org_data,
)

# Create Plan
plan_data = {
    'name': 'Klimatpolitiska rådet',
    'organization': org,
    'primary_language': 'sv',
    'other_languages': [],
    'site_url': 'https://kpr.test.kausal.tech',
}
plan, _ = Plan.objects.update_or_create(
    identifier='kpr',
    defaults=plan_data,
)

# Create CategoryType for transitions
category_type_data = {
    'name': "Omställningar",
    'usable_for_actions': True,
    'hide_category_identifiers': True,
}
category_type, _ = CategoryType.objects.update_or_create(
    plan=plan,
    identifier='transition',
    defaults=category_type_data,
)
metadata, _ = CategoryTypeMetadata.objects.update_or_create(
    type=category_type,
    identifier='impact',
    defaults=dict(
        name='Utsläppsminskning',
        format=CategoryTypeMetadata.MetadataFormat.NUMERIC
    )
)


def import_image(url, credit=''):
    """Download image and import to wagtail."""
    if url is None:
        return None
    filename = os.path.basename(url)
    try:
        image = AplansImage.objects.get(collection_id=plan.root_collection, title=filename)
    except AplansImage.DoesNotExist:
        pass
    else:
        # Update credit
        image.image_credit = credit
        image.save()
        return image
    response = requests.get(url)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        print(f"Could not download {url}: {response}")
        return
    image_file = ImageFile(BytesIO(response.content), name=filename)
    return AplansImage.objects.create(
        title=filename,
        file=image_file,
        collection=plan.root_collection,
        image_credit=credit,
    )


# Create implementation phases
implementation_phase_for_swimlane = {}
for swimlane, identifier, name in [(3, 'proposal', 'Förslag'),
                                   (2, 'inquiry', 'Utredningar'),
                                   (0, 'decided', 'Beslutade')]:
    defaults = {
        'name': name,
    }
    phase, _ = ActionImplementationPhase.objects.update_or_create(
        plan=plan,
        identifier=identifier,
        defaults=defaults,
    )
    implementation_phase_for_swimlane[swimlane] = phase

d = json.load(open('published_sv.json'))

nodes = {}
parent_of = {}

for node in d['publishedBoardVersion']['nodes'].values():
    id = node['id']
    nodes[id] = node
    for child in node['childNodes']:
        assert child not in parent_of
        parent_of[child] = id

actions = {}

for action in d['publishedBoardVersion']['actions'].values():
    id = action['id']
    actions[id] = action

indicators = {}

for indicator in d['publishedBoardVersion']['indicators'].values():
    id = indicator['id']
    indicators[id] = indicator

# Create actions
action_for_uuid = {}
for i, action_data in enumerate(actions.values()):
    identifier = str(i+1)
    properties = action_data['actionProperties']
    implementation_phase = implementation_phase_for_swimlane[properties['swimlane']]
    image_url = properties['imgURL']
    credit = properties.get('imageCredits') or ''
    if image_url:
        image = import_image(image_url, credit)
    else:
        image = None

    if properties['implemented']:
        timestamp = properties['implemented'] // 1000
        start_date = datetime.fromtimestamp(timestamp)
        start_date = timezone.make_aware(start_date, tz)
    else:
        start_date = timezone.now()
    description = properties['description'] or ''
    description = to_rich_text(description)
    defaults = {
        'name': action_data['title'],
        'lead_paragraph': properties['summary'],
        'image': image,
        'description': description,
        'implementation_phase': implementation_phase,
        'start_date': start_date,
    }
    action, _ = Action.objects.update_or_create(
        plan=plan,
        identifier=identifier,
        defaults=defaults,
    )
    assert action_data['id'] not in action_for_uuid
    action_for_uuid[action_data['id']] = action

    # Create action links
    for link in properties.get('readMore', []):
        ActionLink.objects.update_or_create(
            action=action,
            url=link['linkUrl'],
            defaults={
                'title': link.get('title', ''),
            }
        )

    # Categories will be set later

# Create new units that we'll need
Unit.objects.update_or_create(name='passengers per car')
Unit.objects.update_or_create(name='km/kWh')
Unit.objects.update_or_create(name='TWh')
Unit.objects.update_or_create(name='Mt km')
Unit.objects.update_or_create(name='km/l')
Unit.objects.update_or_create(name='km/m³')
Unit.objects.update_or_create(name='t/year')

# Map potential substrings to names of Unit instances in the database
units = {
    '%': '%',
    r'\(%\)': '%',
    'Antal invånare per bil': 'passengers per car',
    'km/kWh': 'km/kWh',
    'TWh': 'TWh',
    'Antal laddbara bilar': 'pcs',
    'Mtonkm': 'Mt km',
    'ton': 't',
    'km/l': 'km/l',
    'Fordonskilometer per m3 bränsle': 'km/m³',
    'kton': 'kt',
    'Antal nybyggda lägenheter som är trähus': 'pcs',
    'ton/år': 't/year',
    'GWh': 'GWh',
    'procent': '%',
    'Antal konverterade oljepannor': 'pcs',
    'Antal konverterade naturgaspannor': 'pcs',
}


def find_whole_word(w):
    return re.compile(r'(^|\s)({0})(\s|$)'.format(w), flags=re.IGNORECASE).search


def guess_unit(v):
    guess = None
    if v:
        for pattern, name in units.items():
            if find_whole_word(pattern)(v):
                if guess:
                    print(f"Multiple unit candidates for string {v}")
                    guess = None
                    break
                guess = Unit.objects.get(name=name)
    if not guess:
        print(f"Could not guess unit for value {v}, using 'no unit'")
        guess = Unit.objects.get(name='no unit')
    return guess


# TODO: Check that all indicators are for leaf transitions (categories)
indicator_for_uuid = {}
# Create an indicator for each category
for i, indicator_data in enumerate(indicators.values()):
    properties = indicator_data['indicatorProperties']
    unit = guess_unit(properties.get('unit'))
    defaults = {
        'name': indicator_data['title'],
        'unit': unit,
        'description': properties.get('description', ''),
    }
    # TBD: What about the following keys?
    # goalDescription, goalExplanation, assessmentDescription, solutionDescription, potentialDescription, outcomeDescription
    indicator, _ = Indicator.objects.update_or_create(
        organization=plan.organization,
        identifier=str(i+1),
        defaults=defaults,
    )
    IndicatorLevel.objects.update_or_create(
        indicator=indicator,
        plan=plan,
        defaults={'level': 'tactical'},
    )
    assert indicator_data['id'] not in indicator_for_uuid
    indicator_for_uuid[indicator_data['id']] = indicator

    # Categories will be set later

# Create a root category for total emissions
root_category, _ = Category.objects.update_or_create(
    type=category_type,
    identifier='root',
    defaults={
        'name': 'Total utsläpp',
        'parent': None,
        'color': '#999999',
    },
)

# Create a category for each node
category_for_uuid = {}
for i, node in enumerate(nodes.values()):
    parent = parent_of.get(node['id'])
    if parent:
        parent = category_for_uuid[parent]
    else:
        parent = root_category
    category_data = {
        'name': node['title'],
        'external_identifier': node['id'],
        'parent': parent,
        'color': SECTOR_COLORS[node['title']] if parent is None or parent is root_category else None
    }
    category, _ = Category.objects.update_or_create(
        type=category_type,
        identifier=str(i+1),
        defaults=category_data,
    )
    assert node['id'] not in category_for_uuid
    category_for_uuid[node['id']] = category

    if 'co2e' in node['nodeProperties']:
        val, _ = CategoryMetadataNumericValue.objects.update_or_create(
            metadata=metadata,
            category=category,
            defaults=dict(
                value=node['nodeProperties']['co2e'],
            )
        )

    # Assign indicators to this category
    for indicator_id in node['indicators']:
        indicator = indicator_for_uuid[indicator_id]
        assert indicator
        indicator.categories.add(category)

    # Assign actions to this category
    if node['childNodes']:
        assert not node['actions']
    else:
        for action_id in node['actions']:
            action = action_for_uuid[action_id]
            assert action
            action.categories.add(category)

# The parent page for all CategoryPage instances should be a Page and we can't rely on its title or slug having a
# particular value. To find it if it exists, look for a page with only category pages as children (and at least one).
categories_page = None
for page in plan.root_page.get_children():
    num_category_pages = page.get_descendants().type(CategoryPage).count()
    if num_category_pages > 0 and num_category_pages == page.get_descendants().count():
        assert categories_page is None
        categories_page = page

if categories_page is None:
    # Create a Page as a parent for all CategoryPages
    categories_page = Page(title='Categories')
    plan.root_page.add_child(instance=categories_page)

# Create a CategoryPage instance for each category
for node_id, category in category_for_uuid.items():
    node = nodes[node_id]
    properties = node['nodeProperties']
    page_body = []

    transition_target_description = properties.get('transitionTargetDescription')
    if transition_target_description:
        description_rich_text = to_rich_text(transition_target_description)
        page_body.append(('text', RichText(description_rich_text)))

    extended_description = properties.get('extendedDescription')
    if extended_description:
        assert set(extended_description.keys()) == {'data', 'type'}, extended_description.keys()
        assert extended_description['type'] == 1
        assert set(extended_description['data'].keys()) == {'texts', 'images'}
        assert len(extended_description['data']['images']) == 1
        assert set(extended_description['data']['images'][0].keys()) == {'imgURL'}
        img_url = extended_description['data']['images'][0]['imgURL']
        texts = extended_description['data']['texts']
        assert len(texts) == 1
        assert list(texts[0].keys()) == ['title', 'body']
        title = texts[0]['title']  # TODO: We ignore this for now.
        body_text = to_rich_text(texts[0]['body'])
        if body_text:
            assert not page_body
            page_body.append(('text', RichText(body_text)))

        # Save image in category, not category page
        image = import_image(img_url)
        category.image = image
        category.save()

    # For those categories without an image from above, fetch one using the transitionTarget field
    if category.image is None:
        target = properties.get('transitionTarget')
        if target:
            target_image_url = f'https://app.climateview.global/assets/images/transition-targets-images/{target}.jpg'
            image = import_image(target_image_url)
            category.image = image
            category.save()

    page_body.append(('related_indicators', {}))

    page_body.append(('category_list', {
        # 'heading': 'TODO',
        # 'lead': 'TODO',
        'style': 'cards',  # or 'table'?
    }))

    page_body.append(('action_list', {}))

    parent = parent_of.get(node_id)
    if parent:
        parent = category_for_uuid[parent].category_page
    if not parent:
        parent = categories_page

    try:
        page = CategoryPage.objects.get(category=category)
        assert page.get_parent().id == parent.id
        page.title = category.name
        page.body = page_body
        page.save()
    except CategoryPage.DoesNotExist:
        page = CategoryPage(title=category.name, category=category, body=page_body)
        parent.add_child(instance=page)

# Create indicator values
for indicator_data in indicators.values():
    indicator = indicator_for_uuid[indicator_data['id']]
    properties = indicator_data['indicatorProperties']
    for outcome in properties['outcome']:
        date_str = outcome['date'].replace("Z", "+00:00")
        date = datetime.fromisoformat(date_str)
        value = None
        if outcome['values']:
            assert len(outcome['values']) == 1
            value = outcome['values'][0]
        if value is not None:
            defaults = {
                'value': value,
            }
            # TODO: dimension categories for this value?
            indicator_value = IndicatorValue.objects.update_or_create(
                indicator=indicator,
                date=date,
                defaults=defaults,
            )

# Create indicator goals
for indicator_data in indicators.values():
    indicator = indicator_for_uuid[indicator_data['id']]
    properties = indicator_data['indicatorProperties']
    for goal in properties['potentialCurve']:
        date_str = goal['date'].replace("Z", "+00:00")
        date = datetime.fromisoformat(date_str)
        value = goal.get('value')
        if value is not None:
            defaults = {
                'value': value,
            }
            indicator_goal = IndicatorGoal.objects.update_or_create(
                plan=plan,
                indicator=indicator,
                date=date,
                defaults=defaults,
            )

# Count occurrences for each organization
org_counter = Counter()
for action_data in actions.values():
    accountable = action_data['actionProperties']['accountable']
    if accountable:
        cleaned = clean_organization_name(accountable)
        org_counter[cleaned] += 1

# from pprint import pprint
# pprint(org_counter)
# pprint(sorted(org_counter.keys()))

# Create DataSource
data_source, _ = DataSource.objects.update_or_create(
    id='kpr',
    defaults={
        'name': 'Klimatpolitiska rådet',
    }
)
print(f"Created data source {data_source}")

# Import organizations with at least a certain number of occurrences
for organization, occurrences in org_counter.items():
    if occurrences >= 5:
        origin_id = str_to_id(organization.lower())
        defaults = {
            'name': organization,
        }
        organization, _ = Organization.objects.update_or_create(
            data_source=data_source,
            origin_id=organization,
            defaults=defaults,
        )
        plan.related_organizations.add(organization)
        print(f"Created organization {organization}")

# Assign organizations to actions
for uuid, action_data in actions.items():
    accountable = action_data['actionProperties']['accountable']
    if accountable:
        cleaned = clean_organization_name(accountable)
        try:
            organization = Organization.objects.get(
                data_source=data_source,
                origin_id=cleaned,
            )
        except Organization.DoesNotExist:
            pass
        else:
            action = action_for_uuid[uuid]
            ActionResponsibleParty.objects.update_or_create(
                action=action,
                organization=organization,
            )
            print(f"Added responsible organization {organization} to action {action}")
