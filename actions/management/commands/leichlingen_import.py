import pandas as pd
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.core.models import Page

from actions.blocks import CategoryListBlock
from actions.models import (
    Action, ActionAttributeType, ActionAttributeTypeChoiceOption, ActionAttributeChoice, ActionAttributeChoiceWithText,
    ActionAttributeRichText, Category, CategoryType, Plan
)
from actions.models.plan import GeneralPlanAdmin
from orgs.models import Organization
from pages.models import ActionListPage, CategoryPage, EmptyPage
from people.models import Person

EXCEL_PROGRESS_TO_IMPLEMENTATION_PHASE_ID = {
    'Implementierung': 'implementation',
    'nicht gestartet': 'not_started',
    'Planung': 'planning',
}

EXCEL_THEME_TO_CATEGORY_IDENTIFIER = {
    'Verwaltung': '1',
    'kommunale Gebäude': '2',
    'Mobilität': '3',
    'Bildung Stadtgesellschaft': '4',
    'Erneuerbare Energien': '5',
    'Bauen und Sanieren': '6',
    'Konsum': '7',
    'Übergeordnetes': '8',
    'Anpassung': '9',
}

ORGANIZATION_CHART = [
    ("Fachbereich 1: Innere Verwaltung, Finanzen, Sicherheit/Ordnung und Bürgerservice", [
        ("10 Zentrale Dienste", []),
        ("20 Kämmerei", []),
        ("32 Ordnungsamt", []),
        ("33 Bürgerbüro + Standesamt", []),
    ]),
    ("Fachbereich 2: Soziales, Jugend, Bildung und Sport", [
        ("40 Bildung und Sport", []),
        ("42 Stadtbücherei", []),
        ("50 Sozialamt", []),
        ("51 Kinder, Jugend und Familie", []),
    ]),
    ("Fachbereich 3: Bauen und Wohnen", [
        ("61 Stadtplanung", []),
        ("62 Zentrales Gebäudemanagement", []),
        ("63 Bauordnung", []),
    ]),
    ("Fachbereich 4: Technische Betriebe Leichlingen", [
        ("66 Tiefbau", []),
        ("67 Bauhof", []),
    ]),
    ("01 Büro Bürgermeister", []),
    ("02 Wirtschaftsförderung", []),
    ("03 EDV", []),
    ("04 E-Government, Datenschutz, Anti-Korruptionsbeauftragter", []),
    ("05 Klimaschutzmanagement", []),
    ("06 Gleichstellungsstelle", []),
    ("14 Rechnungsprüfung", []),
]


def add_org(parent, name, children):
    try:
        org = parent.get_children().get(name=name)
    except Organization.DoesNotExist:
        org = Organization(name=name)
        parent.add_child(instance=org)

    for child_name, grandchildren in children:
        add_org(org, child_name, grandchildren)


def get_organizations(string, root_org):
    """Get list of organizations from the given string"""
    # TODO: What to do with column V ("Beteiligte")?
    # TODO: Ask about these in meeting
    SPECIAL_CASES = {
        'Bürgermeister': ['01 Büro Bürgermeister'],
        # TBD: "62 Gebäudewirtschaft" does not exist according to organization chart; it's "62 Zentrales
        # Gebäudemanagement"
        # '62 Gebäudewirtschaft, 66 Tiefbau': ['62 Gebäudewirtschaft', '66 Tiefbau'],
        '62 Gebäudewirtschaft, 66 Tiefbau': ['62 Zentrales Gebäudemanagement', '66 Tiefbau'],
        '66 Tiefbau, 62 Gebäudewirtschaft': ['66 Tiefbau', '62 Zentrales Gebäudemanagement'],
        '62 Gebäudewirtschaft': ['62 Zentrales Gebäudemanagement'],
        # TBD: BELKAW?
        'BELKAW, 66 Tiefbau': ['66 Tiefbau'],
        '66 Tiefbau, 32 Ordnungsamt': ['66 Tiefbau'],
        '02 Wirtschaftsförderung, 05 Klimaschutzmanagement': ['02 Wirtschaftsförderung', '05 Klimaschutzmanagement'],
        # TBD: "alle Personen in der Verwaltung"?
        'Bürgermeister, alle Personen in der Verwaltung': ['01 Büro Bürgermeister'],
        # TBD: "Kinder- und Jugendparlament"?
        'Kinder- und Jugendparlament, 40 Bildung und Sport, 51 Kinder, Jugend und Familie': [
            '40 Bildung und Sport', '51 Kinder, Jugend und Familie'
        ],
        '51 Kinder, Jugend und Familie, 40 Bildung und Sport': [
            '51 Kinder, Jugend und Familie', '40 Bildung und Sport'
        ],
        # TBD
        'Rheinisch-Bergischer Kreis': [],
        '20 Kämmerei, Bürgermeister': ['20 Kämmerei', '01 Büro Bürgermeister'],
        '61 Stadtplanung, 66 Tiefbau, 67 Bauhof, Technische Betriebe': [
            '61 Stadtplanung', '66 Tiefbau', '67 Bauhof', 'Fachbereich 4: Technische Betriebe Leichlingen'
        ],
        '66 Tiefbau, 67 Bauhof': ['66 Tiefbau', '67 Bauhof'],
        'Technische Betriebe': ['Fachbereich 4: Technische Betriebe Leichlingen'],
    }
    if string in SPECIAL_CASES:
        names = SPECIAL_CASES[string]
    else:
        names = [string]
    return [root_org.get_descendants().get(name=name) for name in names]


def set_categories(action, row, plan):
    # Category type "Thema"
    theme_category_type, _ = CategoryType.objects.get_or_create(
        plan=plan,
        identifier='action',
    )
    theme_category_type.name = "Thema"
    theme_category_type.usable_for_actions = True
    theme_category_type.save()

    # Category "Thema"
    theme_category, _ = Category.objects.get_or_create(
        type=theme_category_type,
        identifier=EXCEL_THEME_TO_CATEGORY_IDENTIFIER[row.theme],
    )
    theme_category.name = row.theme
    theme_category.save()

    action.categories.clear()
    action.categories.add(theme_category)


def set_responsible_organizations(action, row, root_org):
    action.responsible_organizations.clear()
    responsible = get_organizations(row.responsible, root_org)
    for org in responsible:
        action.responsible_organizations.add(org)


def set_action_attribute_ordered_choice(
    action, row, plan, attribute_type_identifier, attribute_type_name, choice_text_to_identifier, choice_column
):
    attribute_type, _ = ActionAttributeType.objects.get_or_create(
        plan=plan,
        identifier=attribute_type_identifier,
    )
    attribute_type.name = attribute_type_name
    attribute_type.format = 'ordered_choice'
    attribute_type.save()

    choice_options = {}
    for text, identifier in choice_text_to_identifier.items():
        aatco, _ = ActionAttributeTypeChoiceOption.objects.get_or_create(
            type=attribute_type,
            identifier=identifier,
        )
        aatco.name = text
        aatco.save()
        choice_options[identifier] = aatco

    choice_identifier = choice_text_to_identifier[row[choice_column].lower()]
    choice_option = choice_options[choice_identifier]
    aac, _ = ActionAttributeChoice.objects.get_or_create(
        type=attribute_type,
        action=action,
        defaults={'choice': choice_option},
    )
    aac.choice = choice_option
    aac.save()


def set_action_attribute_optional_choice(
    action, row, plan, attribute_type_identifier, attribute_type_name, choice_text_to_identifier, choice_column,
    text_column
):
    attribute_type, _ = ActionAttributeType.objects.get_or_create(
        plan=plan,
        identifier=attribute_type_identifier,
    )
    attribute_type.name = attribute_type_name
    attribute_type.format = 'optional_choice'
    attribute_type.save()

    choice_options = {}
    for text, identifier in choice_text_to_identifier.items():
        aatco, _ = ActionAttributeTypeChoiceOption.objects.get_or_create(
            type=attribute_type,
            identifier=identifier,
        )
        aatco.name = text
        aatco.save()
        choice_options[identifier] = aatco

    aac, _ = ActionAttributeChoiceWithText.objects.get_or_create(
        type=attribute_type,
        action=action,
    )
    if type(row[choice_column]) == str:
        choice_identifier = choice_text_to_identifier.get(row[choice_column].lower())
        choice_option = choice_options.get(choice_identifier)
        if choice_option:
            aac.choice = choice_option
    if row[text_column]:
        aac.text = row[text_column]
    aac.save()


def set_action_attribute_rich_text(
    action, row, plan, attribute_type_identifier, attribute_type_name, text_column
):
    attribute_type, _ = ActionAttributeType.objects.get_or_create(
        plan=plan,
        identifier=attribute_type_identifier,
    )
    attribute_type.name = attribute_type_name
    attribute_type.format = 'rich_text'
    attribute_type.save()

    aac, _ = ActionAttributeRichText.objects.get_or_create(
        type=attribute_type,
        action=action,
    )
    if row[text_column]:
        aac.text = row[text_column]
    aac.save()


def set_action_attribute_timeframe(action, row, plan):
    choice_text_to_identifier = {
        'kurzfristig': 'short_term',
        'mittelfristig': 'medium_term',
        'langfristig': 'long_term',
        'mittel- bis langfristig': 'medium_to_long_term',
        'kurz-, mittel und langfristig': 'short_medium_and_long_term',
    }
    set_action_attribute_ordered_choice(
        action,
        row,
        plan,
        attribute_type_identifier='timeframe',
        attribute_type_name="Zeithorizont",
        choice_text_to_identifier=choice_text_to_identifier,
        choice_column='timeframe',
    )


def set_action_attribute_priority(action, row, plan):
    choice_text_to_identifier = {
        'hoch': 'high',
        'mittel': 'medium',
        'niedrig': 'low',
    }
    set_action_attribute_ordered_choice(
        action,
        row,
        plan,
        attribute_type_identifier='priority',
        attribute_type_name="Priorität",
        choice_text_to_identifier=choice_text_to_identifier,
        choice_column='priority',
    )


def set_action_attribute_costs(action, row, plan):
    choice_text_to_identifier = {
        'hoch': 'high',
        'mittel': 'medium',
        'niedrig': 'low',
        'keine': 'none',
    }
    set_action_attribute_optional_choice(
        action,
        row,
        plan,
        attribute_type_identifier='costs',
        attribute_type_name="Kosten",
        choice_text_to_identifier=choice_text_to_identifier,
        choice_column='costs',
        text_column='costs_text',
    )


def set_action_attribute_staff(action, row, plan):
    choice_text_to_identifier = {
        'vorhanden': 'available',
        'zusätzlich': 'additional',
        'prüfen': 'check',
    }
    set_action_attribute_optional_choice(
        action,
        row,
        plan,
        attribute_type_identifier='staff',
        attribute_type_name="Personal",
        choice_text_to_identifier=choice_text_to_identifier,
        choice_column='staff',
        text_column='staff_text',
    )


def set_action_attribute_energy_saving(action, row, plan):
    choice_text_to_identifier = {
        'groß': 'large',
        'mittel': 'medium',
        'klein': 'small',
        'keine': 'none',
    }
    set_action_attribute_optional_choice(
        action,
        row,
        plan,
        attribute_type_identifier='energy_saving',
        attribute_type_name="Energiespareffekte",
        choice_text_to_identifier=choice_text_to_identifier,
        choice_column='energy_saving',
        text_column='energy_saving_text',
    )


def set_action_attribute_emission_reductions(action, row, plan):
    choice_text_to_identifier = {
        'hoch': 'large',
        'mittel': 'medium',
        'niedrig / indirekt': 'small_or_indirect',
        'keine': 'none',
    }
    set_action_attribute_optional_choice(
        action,
        row,
        plan,
        attribute_type_identifier='emission_reductions',
        attribute_type_name="Emissionsreduktionspotential",
        choice_text_to_identifier=choice_text_to_identifier,
        choice_column='emission_reductions',
        text_column='emission_reductions_text',
    )


def set_action_attribute_side_benefits(action, row, plan):
    set_action_attribute_rich_text(
        action,
        row,
        plan,
        attribute_type_identifier='side_benefits',
        attribute_type_name="Wertschöpfung",
        text_column='side_benefits',
    )


def handle_row(row, root_org, plan):
    action, _ = Action.objects.get_or_create(
        plan=plan,
        identifier=row.id,
    )
    action.name = row['name']  # row.name does not give us the right thing
    action.official_name = row.official_name
    action.description = row.official_description
    # TODO: impact?
    action.status = plan.action_statuses.get(identifier='on_time')  # for now assume everything is on time
    implementation_phase_id = EXCEL_PROGRESS_TO_IMPLEMENTATION_PHASE_ID[row.progress]
    action.implementation_phase = plan.action_implementation_phases.get(identifier=implementation_phase_id)
    # TODO: correct use of timeline ("Zeitleiste")?
    try:
        end_year = int(row.timeline)
    except ValueError:
        pass
    else:
        action.end_date = date(end_year, 12, 31)
    action.save()

    set_action_attribute_priority(action, row, plan)
    set_action_attribute_timeframe(action, row, plan)
    set_action_attribute_energy_saving(action, row, plan)
    set_action_attribute_emission_reductions(action, row, plan)
    set_action_attribute_costs(action, row, plan)
    set_action_attribute_staff(action, row, plan)
    set_action_attribute_side_benefits(action, row, plan)
    # TODO: What about column M ("NEU")?
    # TODO: What about column W ("Zielgruppe")?

    set_categories(action, row, plan)
    set_responsible_organizations(action, row, root_org)


def create_theme_pages(theme_category_type, theme_root_page):
    for category in theme_category_type.categories.all():
        try:
            category_page = CategoryPage.objects.get(category=category)
        except CategoryPage.DoesNotExist:
            category_page = CategoryPage(
                category=category,
                title=category.name,
            )
            theme_root_page.add_child(instance=category_page)
        category_page.title = category.name
        category_page.body = [('action_list', {'category_filter': category})]
        category_page.show_in_menus = True
        category_page.show_in_footer = True
        category_page.save()


class Command(BaseCommand):
    help = 'Import data from Leichlingen Excel sheet'

    @transaction.atomic()
    def handle(self, *args, **options):
        sheet = pd.read_excel('Leichlingen Massnahmen_mm_02.04.2022.xlsx', nrows=45)
        sheet.columns = [
            'id',
            'name',
            'official_name',
            'theme',
            'priority',
            'timeframe',
            'timeline',
            'progress_old',
            'progress',
            'official_description',
            'energy_saving_text',
            'energy_saving',
            'NEU',  # ???
            'emission_reductions_text',
            'emission_reductions',
            'side_benefits',
            'costs_text',
            'costs',
            'staff_text',
            'staff',
            'responsible',
            'participating',
            'target_group',
            'first_steps',
            'notes'
        ]

        # Create organizations
        try:
            root_org = Organization.get_root_nodes().get(name="Leichlingen")
        except Organization.DoesNotExist:
            root_org = Organization(name="Leichlingen")
            Organization.add_root(instance=root_org)
        else:
            root_org.get_descendants().delete()
            root_org.refresh_from_db()

        for org_name, children in ORGANIZATION_CHART:
            add_org(root_org, org_name, children)

        # Create plan
        try:
            plan = Plan.objects.get(identifier='leichlingen-klima')
        except Plan.DoesNotExist:
            plan = Plan.create_with_defaults(
                identifier="leichlingen-klima",
                name="Klimastrategie der Blütenstadt Leichlingen",
                short_name="Klimaschutz",
                client_name="Leichlingen",
                client_identifier='leichlingen',
                primary_language='de',
                organization=root_org,
                domain='leichlingen-klima.watch-test.kausal.tech',
            )

        # Create actions etc.
        for _, row in sheet.iterrows():
            handle_row(row, root_org, plan)

        # Create persons
        monika_meves_defaults = {
            'first_name': 'Monika',
            'last_name': 'Meves',
            'title': 'Leitung Klimaschutzmanagement',
            'postal_address': 'Am Büscherhof 1\n42799 Leichlingen',
            'organization': root_org,
            'participated_in_training': True,
        }
        monika_meves, _ = Person.objects.get_or_create(
            email='monika.meves@leichlingen.de',
            defaults=monika_meves_defaults,
        )
        monika_meves.user.is_staff = True
        monika_meves.user.save()

        # Make person general plan admin
        GeneralPlanAdmin.objects.get_or_create(plan=plan, person=monika_meves)

        # Set some page settings
        action_list_page = plan.root_page.get_children().type(ActionListPage).get()
        action_list_page.show_in_menus = True
        action_list_page.show_in_footer = True
        action_list_page.save()

        # Add empty page for categories of type "theme" ("Thema")
        try:
            theme_root_page = plan.root_page.get_children().get(slug='themen')
        except Page.DoesNotExist:
            theme_root_page = EmptyPage(
                title="Themen",
                slug='themen',
                show_in_menus=True,
                show_in_footer=True,
            )
            plan.root_page.add_child(instance=theme_root_page)
        theme_root_page.title = "Themen"
        theme_root_page.show_in_menus = True
        theme_root_page.show_in_footer = True
        theme_root_page.save()

        # Create a category page for each "theme" category
        theme_category_type = CategoryType.objects.get(plan=plan, identifier='action')
        create_theme_pages(theme_category_type, theme_root_page)
