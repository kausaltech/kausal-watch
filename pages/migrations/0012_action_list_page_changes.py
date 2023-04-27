# Generated by Django 3.2.13 on 2022-12-05 09:20

import actions.blocks
from django.db import migrations
import wagtail.core.blocks
import wagtail.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0011_make_page_type_names_translatable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='actionlistpage',
            name='advanced_filters',
            field=wagtail.core.fields.StreamField([('responsible_party', actions.blocks.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.ActionImplementationPhaseFilterBlock()), ('schedule', actions.blocks.ActionScheduleFilterBlock()), ('attribute', wagtail.core.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(label='Attribute type', required=True)), ('show_all_label', wagtail.core.blocks.CharBlock(label="Label for 'show all'", required=False))])), ('category', wagtail.core.blocks.StructBlock([('style', wagtail.core.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')], label='Style')), ('show_all_label', wagtail.core.blocks.CharBlock(label="Label for 'show all'", required=False)), ('category_type', actions.blocks.CategoryTypeChooserBlock(label='Category type', required=True))]))], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_main_bottom',
            field=wagtail.core.fields.StreamField([('official_name', wagtail.core.blocks.StructBlock([('field_label', wagtail.core.blocks.CharBlock(default='', help_text='What label should be used in the public UI for the official name', required=False)), ('caption', wagtail.core.blocks.CharBlock(default='', help_text='Description to show after the field content', required=False))], label='official name')), ('attribute', wagtail.core.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True))], label='Attribute')), ('categories', wagtail.core.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))], label='Category')), ('section', wagtail.core.blocks.StructBlock([('layout', wagtail.core.blocks.ChoiceBlock(choices=[('full-width', 'Full width'), ('grid', 'Grid')])), ('heading', wagtail.core.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('help_text', wagtail.core.blocks.CharBlock(label='Help text', required=False)), ('blocks', wagtail.core.blocks.StreamBlock([('official_name', wagtail.core.blocks.StructBlock([('field_label', wagtail.core.blocks.CharBlock(default='', help_text='What label should be used in the public UI for the official name', required=False)), ('caption', wagtail.core.blocks.CharBlock(default='', help_text='Description to show after the field content', required=False))], label='official name')), ('attribute', wagtail.core.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True))], label='Attribute')), ('categories', wagtail.core.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))], label='Category')), ('lead_paragraph', actions.blocks.ActionLeadParagraphBlock()), ('description', actions.blocks.ActionDescriptionBlock()), ('links', actions.blocks.ActionLinksBlock()), ('tasks', actions.blocks.ActionTasksBlock()), ('merged_actions', actions.blocks.ActionMergedActionsBlock()), ('related_actions', actions.blocks.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.ActionRelatedIndicatorsBlock())], label='Blocks'))], label='Section', required=True)), ('lead_paragraph', actions.blocks.ActionLeadParagraphBlock()), ('description', actions.blocks.ActionDescriptionBlock()), ('links', actions.blocks.ActionLinksBlock()), ('tasks', actions.blocks.ActionTasksBlock()), ('merged_actions', actions.blocks.ActionMergedActionsBlock()), ('related_actions', actions.blocks.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.ActionRelatedIndicatorsBlock())], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_main_top',
            field=wagtail.core.fields.StreamField([('official_name', wagtail.core.blocks.StructBlock([('field_label', wagtail.core.blocks.CharBlock(default='', help_text='What label should be used in the public UI for the official name', required=False)), ('caption', wagtail.core.blocks.CharBlock(default='', help_text='Description to show after the field content', required=False))], label='official name')), ('attribute', wagtail.core.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True))], label='Attribute')), ('categories', wagtail.core.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))], label='Category')), ('section', wagtail.core.blocks.StructBlock([('layout', wagtail.core.blocks.ChoiceBlock(choices=[('full-width', 'Full width'), ('grid', 'Grid')])), ('heading', wagtail.core.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('help_text', wagtail.core.blocks.CharBlock(label='Help text', required=False)), ('blocks', wagtail.core.blocks.StreamBlock([('official_name', wagtail.core.blocks.StructBlock([('field_label', wagtail.core.blocks.CharBlock(default='', help_text='What label should be used in the public UI for the official name', required=False)), ('caption', wagtail.core.blocks.CharBlock(default='', help_text='Description to show after the field content', required=False))], label='official name')), ('attribute', wagtail.core.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(required=True))], label='Attribute')), ('categories', wagtail.core.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(required=True))], label='Category')), ('lead_paragraph', actions.blocks.ActionLeadParagraphBlock()), ('description', actions.blocks.ActionDescriptionBlock()), ('links', actions.blocks.ActionLinksBlock()), ('tasks', actions.blocks.ActionTasksBlock()), ('merged_actions', actions.blocks.ActionMergedActionsBlock()), ('related_actions', actions.blocks.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.ActionRelatedIndicatorsBlock())], label='Blocks'))], label='Section', required=True)), ('lead_paragraph', actions.blocks.ActionLeadParagraphBlock()), ('description', actions.blocks.ActionDescriptionBlock()), ('links', actions.blocks.ActionLinksBlock()), ('tasks', actions.blocks.ActionTasksBlock()), ('merged_actions', actions.blocks.ActionMergedActionsBlock()), ('related_actions', actions.blocks.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.ActionRelatedIndicatorsBlock())], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='main_filters',
            field=wagtail.core.fields.StreamField([('responsible_party', actions.blocks.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.ActionImplementationPhaseFilterBlock()), ('schedule', actions.blocks.ActionScheduleFilterBlock()), ('attribute', wagtail.core.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(label='Attribute type', required=True)), ('show_all_label', wagtail.core.blocks.CharBlock(label="Label for 'show all'", required=False))])), ('category', wagtail.core.blocks.StructBlock([('style', wagtail.core.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')], label='Style')), ('show_all_label', wagtail.core.blocks.CharBlock(label="Label for 'show all'", required=False)), ('category_type', actions.blocks.CategoryTypeChooserBlock(label='Category type', required=True))]))], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='primary_filters',
            field=wagtail.core.fields.StreamField([('responsible_party', actions.blocks.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.ActionImplementationPhaseFilterBlock()), ('schedule', actions.blocks.ActionScheduleFilterBlock()), ('attribute', wagtail.core.blocks.StructBlock([('attribute_type', actions.blocks.ActionAttributeTypeChooserBlock(label='Attribute type', required=True)), ('show_all_label', wagtail.core.blocks.CharBlock(label="Label for 'show all'", required=False))])), ('category', wagtail.core.blocks.StructBlock([('style', wagtail.core.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')], label='Style')), ('show_all_label', wagtail.core.blocks.CharBlock(label="Label for 'show all'", required=False)), ('category_type', actions.blocks.CategoryTypeChooserBlock(label='Category type', required=True))]))], blank=True, null=True),
        ),
    ]
