import pandas as pd
import random
import string
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from actions.models import (
    Action, AttributeType, AttributeTypeChoiceOption, AttributeChoice, AttributeRichText, Category, CategoryType, Plan
)
from orgs.models import Organization
from pages.models import ActionListPage


# Transform text with line breaks to rich text
def generate_block_key():
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(random.choices(alphabet, k=5))


def string_to_rich_text(s):
    paragraphs = [p.strip() for p in s.split('\n')]
    paragraphs = [f'<p data-block-key="{generate_block_key()}">{p}</p>' for p in paragraphs if p]
    return ''.join(paragraphs)


class Command(BaseCommand):
    help = 'Import data from Leichlingen Mobilität Excel sheet'

    @transaction.atomic()
    def handle(self, *args, **options):
        sheet = pd.read_excel('Maßnahmenvorlage_Mobilität_07.05.2023.xlsx') #, nrows=45)
        sheet.columns = [
            'id',
            'name',
            'official_name',
            'theme',
            'ad_hoc',
            # 'lz_kurze_wege',
            # 'lz_nachhaltig_mobil',
            # 'lz_vernetzt',
            # 'lz_stadtvertraeglich_mobil',
            # 'lz_vorreiter',
            'lz_1',
            'lz_2',
            'lz_3',
            'lz_4',
            'lz_5',
            'umsetzung',
            'wirkung',
            'kosten',
            'kurzbeschreibung',
            'bausteine',
            'beteiligte',
            'schnittstellen_steckbriefe',
            'schnittstellen_planwerke',
            'foerdermoeglichkeiten',
            'hinweis',
        ]
        sheet.wirkung.fillna('Undefiniert', inplace=True)
        sheet.kosten.fillna('Undefiniert', inplace=True)
        sheet.fillna('', inplace=True)

        for column in ['kurzbeschreibung', 'bausteine', 'beteiligte', 'schnittstellen_steckbriefe', 'schnittstellen_planwerke', 'foerdermoeglichkeiten']:
            sheet[column] = getattr(sheet, column).str.replace(' •', '\n•')
            sheet[column] = getattr(sheet, column).apply(string_to_rich_text)

        leichlingen_org = Organization.get_root_nodes().get(name="Leichlingen")
        try:
            self.plan = Plan.objects.get(identifier='leichlingen-mobilitaet')
        except Plan.DoesNotExist:
            self.plan = Plan.create_with_defaults(
                identifier="leichlingen-mobilitaet",
                short_name="Leichlingens Mobilitätskonzept",
                name="Mobilitätskonzept der Blütenstadt Leichlingen",
                primary_language='de',
                organization=leichlingen_org,
                domain='leichlingen-mobilitaet.watch-test.kausal.tech',
            )

        for i, row in sheet.iterrows():
            self.handle_row(row)

        content_fields = ['primary_filters', 'main_filters', 'advanced_filters', 'details_main_top', 'details_main_bottom', 'details_aside']
        action_list_page = self.plan.root_page.get_children().type(ActionListPage).get().specific
        if not any(getattr(action_list_page, field) for field in content_fields):
            action_list_page.set_default_content_blocks()
            self.plan.invalidate_cache()

    def set_action_attribute_ordered_choice(self, action, row, attribute_type_name, choice_text_to_identifier, choice_column, has_zero_option=False):
        attribute_type_kwargs = dict(
            object_content_type=ContentType.objects.get_for_model(action),
            scope_content_type=ContentType.objects.get_for_model(self.plan),
            scope_id=self.plan.id,
            name=attribute_type_name,
        )
        try:
            attribute_type = AttributeType.objects.get(**attribute_type_kwargs)
        except AttributeType.DoesNotExist:
            attribute_type = AttributeType.objects.create(
                **attribute_type_kwargs,
            )
        attribute_type.format = 'ordered_choice'
        attribute_type.has_zero_option = has_zero_option
        attribute_type.save()

        choice_options = {}
        for text, identifier in choice_text_to_identifier.items():
            atco_kwargs = dict(
                type=attribute_type,
                name=text,
            )
            try:
                aatco = AttributeTypeChoiceOption.objects.get(**atco_kwargs)
            except AttributeTypeChoiceOption.DoesNotExist:
                aatco = AttributeTypeChoiceOption.objects.create(**atco_kwargs)
            choice_options[identifier] = aatco

        choice_identifier = choice_text_to_identifier[row[choice_column]]
        choice_option = choice_options[choice_identifier]
        aac, _ = AttributeChoice.objects.get_or_create(
            type=attribute_type,
            content_type=ContentType.objects.get_for_model(action),
            object_id=action.id,
            defaults={'choice': choice_option},
        )
        aac.choice = choice_option
        aac.save()

    def set_action_attribute_rich_text(self, action, row, attribute_type_name, text_column):
        attribute_type_kwargs = dict(
            object_content_type=ContentType.objects.get_for_model(action),
            scope_content_type=ContentType.objects.get_for_model(self.plan),
            scope_id=self.plan.id,
            name=attribute_type_name,
        )
        try:
            attribute_type = AttributeType.objects.get(**attribute_type_kwargs)
        except AttributeType.DoesNotExist:
            attribute_type = AttributeType.objects.create(
                **attribute_type_kwargs,
            )
        attribute_type.format = 'rich_text'
        attribute_type.save()

        aac, _ = AttributeRichText.objects.get_or_create(
            type=attribute_type,
            content_type=ContentType.objects.get_for_model(action),
            object_id=action.id,
        )
        if row[text_column]:
            aac.text = row[text_column]
        aac.save()


    def set_action_attribute_ad_hoc(self, action, row):
        choice_text_to_identifier = {
            'nein': 'nein',
            'ja': 'ja',
        }
        self.set_action_attribute_ordered_choice(
            action,
            row,
            attribute_type_name="Ad-hoc Maßnahme",
            choice_text_to_identifier=choice_text_to_identifier,
            choice_column='ad_hoc',
            has_zero_option=True,
        )


    def set_action_attribute_umsetzung(self, action, row):
        choice_text_to_identifier = {
            'Kurzfristig': 'kurzfristig',
            'Mittelfristig': 'mittelfristig',
            'Langfristig': 'langfristig',
            'Daueraufgabe': 'daueraufgabe',
        }
        self.set_action_attribute_ordered_choice(
            action,
            row,
            attribute_type_name="Umsetzung",
            choice_text_to_identifier=choice_text_to_identifier,
            choice_column='umsetzung',
        )

    def set_action_attribute_wirkung(self, action, row):
        choice_text_to_identifier = {
            'Undefiniert': 'undefiniert',
            'Klein': 'klein',
            'Mittel': 'mittel',
            'Groß': 'gross',
            'Sehr groß': 'sehr-gross',
        }
        self.set_action_attribute_ordered_choice(
            action,
            row,
            attribute_type_name="Wirkung",
            choice_text_to_identifier=choice_text_to_identifier,
            choice_column='wirkung',
        )

    def set_action_attribute_kosten(self, action, row):
        choice_text_to_identifier = {
            'Undefiniert': 'undefiniert',
            'Niedrig': 'niedrig',
            'Mittel': 'mittel',
            'Hoch': 'hoch',
            'Sehr hoch': 'sehr-hoch',
        }
        self.set_action_attribute_ordered_choice(
            action,
            row,
            attribute_type_name="Kosten",
            choice_text_to_identifier=choice_text_to_identifier,
            choice_column='kosten',
        )

    def set_action_attribute_bausteine(self, action, row):
        self.set_action_attribute_rich_text(
            action,
            row,
            attribute_type_name="Bausteine / Vorgehen",
            text_column='bausteine',
        )


    def set_action_attribute_beteiligte(self, action, row):
        self.set_action_attribute_rich_text(
            action,
            row,
            attribute_type_name="Beteiligte",
            text_column='beteiligte',
        )

    def set_action_attribute_schnittstellen_steckbriefe(self, action, row):
        self.set_action_attribute_rich_text(
            action,
            row,
            attribute_type_name="Schnittstellen: Andere Steckbriefe",
            text_column='schnittstellen_steckbriefe',
        )

    def set_action_attribute_schnittstellen_planwerke(self, action, row):
        self.set_action_attribute_rich_text(
            action,
            row,
            attribute_type_name="Schnittstellen: Weiter Planwerke",
            text_column='schnittstellen_planwerke',
        )

    def set_action_attribute_foerdermoeglichkeiten(self, action, row):
        self.set_action_attribute_rich_text(
            action,
            row,
            attribute_type_name="Fördermöglichkeiten",
            text_column='foerdermoeglichkeiten',
        )

    def set_categories(self, action, row):
        action.categories.clear()

        # Category type "Handlungsfeld"
        handlungsfeld_category_type, _ = CategoryType.objects.get_or_create(
            plan=self.plan,
            identifier='handlungsfeld',
        )
        handlungsfeld_category_type.name = "Handlungsfeld"
        handlungsfeld_category_type.usable_for_actions = True
        handlungsfeld_category_type.editable_for_actions = True
        handlungsfeld_category_type.save()

        self.plan.primary_action_classification = handlungsfeld_category_type
        self.plan.save()

        # Category Leitziel for current row
        HANDLUNGSFELDER = {
            '1': 'ÖPNV und Vernetzte Mobilität',
            '2': 'Nahmobilität mit dem Rad und zu Fuß',
            '3': 'Ortslagen und Ortskerne',
            '4': 'fließender Verkehr',
            '5': 'Mobilitätsmanagement und Öffentlichkeitsarbeit',
        }
        for identifier, name in HANDLUNGSFELDER.items():
            handlungsfeld_category, _ = Category.objects.get_or_create(
                type=handlungsfeld_category_type,
                identifier=identifier,
            )
            handlungsfeld_category.name = name
            handlungsfeld_category.save()
            if row.theme == name:
                action.categories.add(handlungsfeld_category)
        if not action.categories.exists():
            print(row.theme)
            assert False

        # Category type "Leitziel"
        leitziel_category_type, _ = CategoryType.objects.get_or_create(
            plan=self.plan,
            identifier='leitziel',
        )
        leitziel_category_type.name = "Leitziel"
        leitziel_category_type.select_widget = 'multiple'
        leitziel_category_type.usable_for_actions = True
        leitziel_category_type.editable_for_actions = True
        leitziel_category_type.save()

        # Category Leitziel for current row
        LEITZIELE = {
            '1': 'Die Blütenstadt der kurzen Wege',
            '2': 'Die nachhaltig mobile Blütenstadt',
            '3': 'Die vernetzte Blütenstadt',
            '4': 'Stadtverträglich mobil in der Blütenstadt',
            '5': 'Die Blütenstadt als Vorreiter',
        }
        for identifier, name in LEITZIELE.items():
            lz_category, _ = Category.objects.get_or_create(
                type=leitziel_category_type,
                identifier=identifier,
            )
            lz_category.name = name
            lz_category.save()
            column_name = 'lz_' + identifier.replace('-', '_')
            if row[column_name] == 'ja':
                action.categories.add(lz_category)

    def handle_row(self, row):
        action, _ = Action.objects.get_or_create(
            plan=self.plan,
            identifier=row.id,
        )
        action.name = row['name']  # row.name does not give us the right thing
        action.official_name = row.official_name
        action.description = row.kurzbeschreibung
        action.status = self.plan.action_statuses.get(identifier='on_time')  # for now assume everything is on time
        action.implementation_phase = self.plan.action_implementation_phases.get(identifier='planning')
        action.save()

        self.set_action_attribute_ad_hoc(action, row)
        self.set_action_attribute_umsetzung(action, row)
        self.set_action_attribute_wirkung(action, row)
        self.set_action_attribute_kosten(action, row)
        self.set_action_attribute_bausteine(action, row)
        self.set_action_attribute_beteiligte(action, row)
        self.set_action_attribute_schnittstellen_steckbriefe(action, row)
        self.set_action_attribute_schnittstellen_planwerke(action, row)
        self.set_action_attribute_foerdermoeglichkeiten(action, row)
        self.set_categories(action, row)
