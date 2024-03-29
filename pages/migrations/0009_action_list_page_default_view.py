# Generated by Django 3.2.13 on 2022-10-24 13:12

import actions.blocks
from django.db import migrations, models
import pages.blocks
import wagtail.blocks
import wagtail.fields


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0008_privacy_policy_and_accessibility_statement'),
    ]

    operations = [
        migrations.AddField(
            model_name='actionlistpage',
            name='default_view',
            field=models.CharField(choices=[('cards', 'cards'), ('dashboard', 'dashboard')], default='cards', max_length=30, verbose_name='default view'),
        ),
        migrations.AlterField(
            model_name='accessibilitystatementpage',
            name='body',
            field=wagtail.fields.StreamField([('text', wagtail.blocks.RichTextBlock(label='Text')), ('compliance_status', pages.blocks.AccessibilityStatementComplianceStatusBlock()), ('preparation', pages.blocks.AccessibilityStatementPreparationInformationBlock()), ('contact_information', wagtail.blocks.StructBlock([('publisher_name', wagtail.blocks.CharBlock()), ('email', wagtail.blocks.CharBlock())]))], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='advanced_filters',
            field=wagtail.fields.StreamField([('responsible_party', actions.blocks.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.ActionImplementationPhaseFilterBlock()), ('schedule', actions.blocks.ActionScheduleFilterBlock()), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True)), ('show_all_label', wagtail.blocks.CharBlock(required=False))])), ('category', wagtail.blocks.StructBlock([('style', wagtail.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')])), ('show_all_label', wagtail.blocks.CharBlock(required=False)), ('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))]))], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_aside',
            field=wagtail.fields.StreamField([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True))], label='Attribute', required=True)), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))], label='Category', required=True)), ('schedule', actions.blocks.ActionScheduleBlock()), ('contact_persons', actions.blocks.ActionContactPersonsBlock()), ('responsible_parties', actions.blocks.ActionResponsiblePartiesBlock())], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_main_bottom',
            field=wagtail.fields.StreamField([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True))], label='Attribute', required=True)), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))], label='Category', required=True)), ('lead_paragraph', actions.blocks.ActionLeadParagraphBlock()), ('description', actions.blocks.ActionDescriptionBlock()), ('official_name', actions.blocks.ActionOfficialNameBlock()), ('links', actions.blocks.ActionLinksBlock()), ('tasks', actions.blocks.ActionTasksBlock()), ('merged_actions', actions.blocks.ActionMergedActionsBlock()), ('related_actions', actions.blocks.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.ActionRelatedIndicatorsBlock())], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_main_top',
            field=wagtail.fields.StreamField([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True))], label='Attribute', required=True)), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))], label='Category', required=True)), ('lead_paragraph', actions.blocks.ActionLeadParagraphBlock()), ('description', actions.blocks.ActionDescriptionBlock()), ('official_name', actions.blocks.ActionOfficialNameBlock()), ('links', actions.blocks.ActionLinksBlock()), ('tasks', actions.blocks.ActionTasksBlock()), ('merged_actions', actions.blocks.ActionMergedActionsBlock()), ('related_actions', actions.blocks.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.ActionRelatedIndicatorsBlock())], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='main_filters',
            field=wagtail.fields.StreamField([('responsible_party', actions.blocks.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.ActionImplementationPhaseFilterBlock()), ('schedule', actions.blocks.ActionScheduleFilterBlock()), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True)), ('show_all_label', wagtail.blocks.CharBlock(required=False))])), ('category', wagtail.blocks.StructBlock([('style', wagtail.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')])), ('show_all_label', wagtail.blocks.CharBlock(required=False)), ('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))]))], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='primary_filters',
            field=wagtail.fields.StreamField([('responsible_party', actions.blocks.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.ActionImplementationPhaseFilterBlock()), ('schedule', actions.blocks.ActionScheduleFilterBlock()), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True)), ('show_all_label', wagtail.blocks.CharBlock(required=False))])), ('category', wagtail.blocks.StructBlock([('style', wagtail.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')])), ('show_all_label', wagtail.blocks.CharBlock(required=False)), ('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))]))], blank=True, null=True),
        ),
    ]
