# Generated by Django 3.2.13 on 2022-12-05 09:24

import actions.blocks
from django.db import migrations
import kausal_watch_extensions.blocks
import wagtail.core.blocks
import wagtail.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0012_action_list_page_changes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='staticpage',
            name='body',
            field=wagtail.core.fields.StreamField([('heading', wagtail.core.blocks.CharBlock(form_classname='full title', label='Heading')), ('paragraph', wagtail.core.blocks.RichTextBlock(label='Paragraph')), ('qa_section', wagtail.core.blocks.StructBlock([('heading', wagtail.core.blocks.CharBlock(form_classname='title', heading='Title', required=False)), ('questions', wagtail.core.blocks.ListBlock(wagtail.core.blocks.StructBlock([('question', wagtail.core.blocks.CharBlock(heading='Question')), ('answer', wagtail.core.blocks.RichTextBlock(heading='Answer'))])))], icon='help', label='Questions & Answers')), ('category_list', wagtail.core.blocks.StructBlock([('category_type', actions.blocks.CategoryTypeChooserBlock(label='Category type', required=False)), ('heading', wagtail.core.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.core.blocks.RichTextBlock(label='Lead', required=False)), ('style', wagtail.core.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table')]))], label='Category list')), ('category_tree_map', wagtail.core.blocks.StructBlock([('heading', wagtail.core.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.core.blocks.RichTextBlock(label='Lead', required=False)), ('category_type', actions.blocks.CategoryTypeChooserBlock(label='Category type', required=True)), ('value_attribute', actions.blocks.CategoryAttributeTypeChooserBlock(label='Value attribute', required=True))], label='Category tree map')), ('cartography_visualisation_block', wagtail.core.blocks.StructBlock([('account', kausal_watch_extensions.blocks.CartographyProviderCredentialsChooserBlock(label='Map Provider Credentials')), ('style_url', wagtail.core.blocks.CharBlock(label='Style URL', required=True))], label='Map Visualisation'))], blank=True, null=True),
        ),
    ]
