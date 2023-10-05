import actions.blocks
import actions.blocks.action_content
import actions.blocks.action_list
import actions.blocks.choosers
import actions.blocks.filters
from django.db import migrations, models
import django.db.models.deletion
import indicators.blocks
import kausal_watch_extensions.blocks
import modelcluster.fields
import pages.blocks
import reports.blocks.choosers
import wagtail.blocks
import wagtail.fields
import wagtail.images.blocks
from uuid import uuid4

DEFAULT_COLUMN_BLOCK_TYPES = [
    'identifier',
    'name',
    'implementation_phase',
    'tasks',
    'responsible_parties',
    'indicators',
    'updated_at',
]


def create_default_dashboard_columns(apps, schema_editor):
    ActionListPage = apps.get_model('pages', 'ActionListPage')
    for page in ActionListPage.objects.all():
        page.dashboard_columns = [
            {
                'id': str(uuid4()),
                'type': block_type,
                'value': {'column_label': ''},
            } for block_type in DEFAULT_COLUMN_BLOCK_TYPES
        ]
        page.save(update_fields=['dashboard_columns'])


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0095_action_dashboard_columns'),
        ('pages', '0025_fix_responsible_party_block_values'),
    ]

    operations = [
        migrations.AddField(
            model_name='actionlistpage',
            name='dashboard_columns',
            field=wagtail.fields.StreamField([('identifier', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('name', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('implementation_phase', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('status', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('tasks', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('responsible_parties', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('indicators', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('updated_at', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('organization', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))])), ('imact', wagtail.blocks.StructBlock([('column_label', wagtail.blocks.CharBlock(help_text='Label for the column to be used instead of the default', label='Label', required=False))]))], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='advanced_filters',
            field=wagtail.fields.StreamField([('responsible_party', actions.blocks.filters.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.filters.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.filters.ActionImplementationPhaseFilterBlock()), ('status', actions.blocks.filters.ActionStatusFilterBlock()), ('schedule', actions.blocks.filters.ActionScheduleFilterBlock()), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True)), ('show_all_label', wagtail.blocks.CharBlock(label="Label for 'show all'", required=False))])), ('category', wagtail.blocks.StructBlock([('style', wagtail.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')], label='Style')), ('show_all_label', wagtail.blocks.CharBlock(label="Label for 'show all'", required=False)), ('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True)), ('depth', wagtail.blocks.IntegerBlock(help_text='How many levels of category hierarchy to show', label='Depth', min_value=1, required=False))])), ('plan', actions.blocks.filters.PlanFilterBlock())], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_aside',
            field=wagtail.fields.StreamField([('responsible_parties', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(default='', help_text='Heading to show instead of the default', required=False))], required=True)), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True))], required=True)), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True))], required=True)), ('schedule', actions.blocks.action_content.ActionScheduleBlock()), ('contact_persons', actions.blocks.action_content.ActionContactPersonsBlock())], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_main_bottom',
            field=wagtail.fields.StreamField([('section', wagtail.blocks.StructBlock([('layout', wagtail.blocks.ChoiceBlock(choices=[('full-width', 'Full width'), ('grid', 'Grid')])), ('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('help_text', wagtail.blocks.CharBlock(label='Help text', required=False)), ('blocks', wagtail.blocks.StreamBlock([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True))])), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True))]))], label='Blocks'))], required=True)), ('official_name', wagtail.blocks.StructBlock([('field_label', wagtail.blocks.CharBlock(default='', help_text='What label should be used in the public UI for the official name?', label='Field label', required=False)), ('caption', wagtail.blocks.CharBlock(default='', help_text='Description to show after the field content', label='Caption', required=False))])), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True))])), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True))])), ('contact_form', actions.blocks.action_content.ActionContactFormBlock(required=True)), ('report_comparison', wagtail.blocks.StructBlock([('report_type', reports.blocks.choosers.ReportTypeChooserBlock(required=True)), ('report_field', reports.blocks.choosers.ReportTypeFieldChooserBlock(label='UUID of report field', required=True))])), ('lead_paragraph', actions.blocks.action_content.ActionLeadParagraphBlock()), ('description', actions.blocks.action_content.ActionDescriptionBlock()), ('links', actions.blocks.action_content.ActionLinksBlock()), ('tasks', actions.blocks.action_content.ActionTasksBlock()), ('merged_actions', actions.blocks.action_content.ActionMergedActionsBlock()), ('related_actions', actions.blocks.action_content.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.action_content.ActionRelatedIndicatorsBlock())], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='details_main_top',
            field=wagtail.fields.StreamField([('section', wagtail.blocks.StructBlock([('layout', wagtail.blocks.ChoiceBlock(choices=[('full-width', 'Full width'), ('grid', 'Grid')])), ('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('help_text', wagtail.blocks.CharBlock(label='Help text', required=False)), ('blocks', wagtail.blocks.StreamBlock([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True))])), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True))]))], label='Blocks'))], required=True)), ('official_name', wagtail.blocks.StructBlock([('field_label', wagtail.blocks.CharBlock(default='', help_text='What label should be used in the public UI for the official name?', label='Field label', required=False)), ('caption', wagtail.blocks.CharBlock(default='', help_text='Description to show after the field content', label='Caption', required=False))])), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True))])), ('categories', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True))])), ('contact_form', actions.blocks.action_content.ActionContactFormBlock(required=True)), ('report_comparison', wagtail.blocks.StructBlock([('report_type', reports.blocks.choosers.ReportTypeChooserBlock(required=True)), ('report_field', reports.blocks.choosers.ReportTypeFieldChooserBlock(label='UUID of report field', required=True))])), ('lead_paragraph', actions.blocks.action_content.ActionLeadParagraphBlock()), ('description', actions.blocks.action_content.ActionDescriptionBlock()), ('links', actions.blocks.action_content.ActionLinksBlock()), ('tasks', actions.blocks.action_content.ActionTasksBlock()), ('merged_actions', actions.blocks.action_content.ActionMergedActionsBlock()), ('related_actions', actions.blocks.action_content.ActionRelatedActionsBlock()), ('related_indicators', actions.blocks.action_content.ActionRelatedIndicatorsBlock())], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='main_filters',
            field=wagtail.fields.StreamField([('responsible_party', actions.blocks.filters.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.filters.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.filters.ActionImplementationPhaseFilterBlock()), ('status', actions.blocks.filters.ActionStatusFilterBlock()), ('schedule', actions.blocks.filters.ActionScheduleFilterBlock()), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True)), ('show_all_label', wagtail.blocks.CharBlock(label="Label for 'show all'", required=False))])), ('category', wagtail.blocks.StructBlock([('style', wagtail.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')], label='Style')), ('show_all_label', wagtail.blocks.CharBlock(label="Label for 'show all'", required=False)), ('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True)), ('depth', wagtail.blocks.IntegerBlock(help_text='How many levels of category hierarchy to show', label='Depth', min_value=1, required=False))])), ('plan', actions.blocks.filters.PlanFilterBlock())], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='actionlistpage',
            name='primary_filters',
            field=wagtail.fields.StreamField([('responsible_party', actions.blocks.filters.ResponsiblePartyFilterBlock()), ('primary_org', actions.blocks.filters.PrimaryOrganizationFilterBlock()), ('implementation_phase', actions.blocks.filters.ActionImplementationPhaseFilterBlock()), ('status', actions.blocks.filters.ActionStatusFilterBlock()), ('schedule', actions.blocks.filters.ActionScheduleFilterBlock()), ('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(required=True)), ('show_all_label', wagtail.blocks.CharBlock(label="Label for 'show all'", required=False))])), ('category', wagtail.blocks.StructBlock([('style', wagtail.blocks.ChoiceBlock(choices=[('dropdown', 'Dropdown'), ('buttons', 'Buttons')], label='Style')), ('show_all_label', wagtail.blocks.CharBlock(label="Label for 'show all'", required=False)), ('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True)), ('depth', wagtail.blocks.IntegerBlock(help_text='How many levels of category hierarchy to show', label='Depth', min_value=1, required=False))])), ('plan', actions.blocks.filters.PlanFilterBlock())], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='categorypage',
            name='body',
            field=wagtail.fields.StreamField([('text', wagtail.blocks.RichTextBlock(label='Text')), ('qa_section', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(form_classname='title', heading='Title', required=False)), ('questions', wagtail.blocks.ListBlock(wagtail.blocks.StructBlock([('question', wagtail.blocks.CharBlock(heading='Question')), ('answer', wagtail.blocks.RichTextBlock(heading='Answer'))])))], icon='help')), ('indicator_group', indicators.blocks.IndicatorGroupBlock()), ('related_indicators', indicators.blocks.RelatedIndicatorsBlock()), ('category_list', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=False)), ('category', actions.blocks.choosers.CategoryChooserBlock(required=False)), ('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False)), ('style', wagtail.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table')], label='Style'))])), ('action_list', wagtail.blocks.StructBlock([('category_filter', actions.blocks.choosers.CategoryChooserBlock(label='Filter on category'))])), ('embed', wagtail.blocks.StructBlock([('embed', wagtail.blocks.StructBlock([('url', wagtail.blocks.CharBlock(label='URL')), ('height', wagtail.blocks.ChoiceBlock(choices=[('s', 'small'), ('m', 'medium'), ('l', 'large')], label='Size'))]))]))], blank=True, null=True, use_json_field=True),
        ),
        migrations.AlterField(
            model_name='categorytypepagelevellayout',
            name='layout_aside',
            field=wagtail.fields.StreamField([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.CategoryAttributeTypeChooserBlock(required=True))]))], blank=True, null=True, use_json_field=True, verbose_name='layout aside'),
        ),
        migrations.AlterField(
            model_name='categorytypepagelevellayout',
            name='layout_main_bottom',
            field=wagtail.fields.StreamField([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.CategoryAttributeTypeChooserBlock(required=True))])), ('body', wagtail.blocks.StructBlock([])), ('category_list', wagtail.blocks.StructBlock([])), ('contact_form', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(label='Heading', required=False)), ('description', wagtail.blocks.CharBlock(label='Description', required=False))]))], blank=True, null=True, use_json_field=True, verbose_name='layout main bottom'),
        ),
        migrations.AlterField(
            model_name='categorytypepagelevellayout',
            name='layout_main_top',
            field=wagtail.fields.StreamField([('attribute', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.CategoryAttributeTypeChooserBlock(required=True))])), ('progress', wagtail.blocks.StructBlock([('basis', wagtail.blocks.ChoiceBlock(choices=[('implementation_phase', 'Implementation phase'), ('status', 'Status')], label='Basis'))]))], blank=True, null=True, use_json_field=True, verbose_name='layout main top'),
        ),
        migrations.AlterField(
            model_name='categorytypepagelevellayout',
            name='level',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='level_layouts', to='actions.categorylevel', verbose_name='level'),
        ),
        migrations.AlterField(
            model_name='categorytypepagelevellayout',
            name='page',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='level_layouts', to='pages.categorytypepage', verbose_name='page'),
        ),
        migrations.AlterField(
            model_name='indicatorlistpage',
            name='display_insights',
            field=models.BooleanField(default=True, help_text='Should insight network be shown for indicators?', verbose_name='Display insights'),
        ),
        migrations.AlterField(
            model_name='planrootpage',
            name='body',
            field=wagtail.fields.StreamField([('front_page_hero', wagtail.blocks.StructBlock([('layout', wagtail.blocks.ChoiceBlock(choices=[('big_image', 'Big image'), ('small_image', 'Small image')])), ('image', wagtail.images.blocks.ImageChooserBlock()), ('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False))])), ('category_list', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=False)), ('category', actions.blocks.choosers.CategoryChooserBlock(required=False)), ('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False)), ('style', wagtail.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table')], label='Style'))])), ('indicator_group', indicators.blocks.IndicatorGroupBlock()), ('indicator_highlights', indicators.blocks.IndicatorHighlightsBlock()), ('indicator_showcase', wagtail.blocks.StructBlock([('title', wagtail.blocks.CharBlock(required=False)), ('body', wagtail.blocks.RichTextBlock(required=False)), ('indicator', indicators.blocks.IndicatorChooserBlock()), ('link_button', wagtail.blocks.StructBlock([('text', wagtail.blocks.CharBlock(required=False)), ('page', wagtail.blocks.PageChooserBlock(required=False))])), ('indicator_is_normalized', wagtail.blocks.BooleanBlock(required=False))])), ('action_highlights', actions.blocks.action_list.ActionHighlightsBlock()), ('related_plans', actions.blocks.RelatedPlanListBlock()), ('cards', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock()), ('lead', wagtail.blocks.CharBlock(required=False)), ('cards', wagtail.blocks.ListBlock(wagtail.blocks.StructBlock([('image', wagtail.images.blocks.ImageChooserBlock(required=False)), ('heading', wagtail.blocks.CharBlock()), ('content', wagtail.blocks.CharBlock(required=False)), ('link', wagtail.blocks.CharBlock(required=False))])))])), ('action_links', wagtail.blocks.StructBlock([('cards', wagtail.blocks.ListBlock(wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(label='Heading')), ('lead', wagtail.blocks.CharBlock(label='Lead')), ('category', actions.blocks.choosers.CategoryChooserBlock())]), label='Links'))], label='Links to actions in specific category')), ('text', wagtail.blocks.RichTextBlock(label='Text')), ('action_status_graphs', pages.blocks.ActionStatusGraphsBlock()), ('category_tree_map', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False)), ('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True)), ('value_attribute', actions.blocks.choosers.CategoryAttributeTypeChooserBlock(label='Value field', required=True))]))], use_json_field=True),
        ),
        migrations.AlterField(
            model_name='staticpage',
            name='body',
            field=wagtail.fields.StreamField([('paragraph', wagtail.blocks.RichTextBlock(label='Paragraph')), ('qa_section', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(form_classname='title', heading='Title', required=False)), ('questions', wagtail.blocks.ListBlock(wagtail.blocks.StructBlock([('question', wagtail.blocks.CharBlock(heading='Question')), ('answer', wagtail.blocks.RichTextBlock(heading='Answer'))])))], icon='help')), ('category_list', wagtail.blocks.StructBlock([('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=False)), ('category', actions.blocks.choosers.CategoryChooserBlock(required=False)), ('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False)), ('style', wagtail.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table')], label='Style'))])), ('embed', wagtail.blocks.StructBlock([('embed', wagtail.blocks.StructBlock([('url', wagtail.blocks.CharBlock(label='URL')), ('height', wagtail.blocks.ChoiceBlock(choices=[('s', 'small'), ('m', 'medium'), ('l', 'large')], label='Size'))]))])), ('category_tree_map', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False)), ('category_type', actions.blocks.choosers.CategoryTypeChooserBlock(required=True)), ('value_attribute', actions.blocks.choosers.CategoryAttributeTypeChooserBlock(label='Value field', required=True))])), ('cartography_visualisation_block', wagtail.blocks.StructBlock([('account', kausal_watch_extensions.blocks.CartographyProviderCredentialsChooserBlock(label='Map provider credentials')), ('style', wagtail.blocks.CharBlock(choices=[], label='Map style', required=True, validators=[])), ('style_overrides', wagtail.blocks.TextBlock(label='Map labels', required=False))], label='Map visualization'))], blank=True, null=True, use_json_field=True),
        ),
        migrations.RunPython(create_default_dashboard_columns),
    ]
