# Generated by Django 3.2.12 on 2022-03-04 12:41

import actions.blocks
from django.db import migrations, models
import django.db.models.deletion
import indicators.blocks
import wagtail.blocks
import wagtail.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0014_categorytype_i18n'),
        ('pages', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='categorypage',
            name='body',
            field=wagtail.fields.StreamField([('text', wagtail.blocks.RichTextBlock(label='Text')), ('indicator_group', indicators.blocks.IndicatorGroupBlock()), ('related_indicators', indicators.blocks.RelatedIndicatorsBlock()), ('category_list', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False)), ('style', wagtail.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table'), ('treemap', 'Tree map')]))], label='Category list')), ('action_list', wagtail.blocks.StructBlock([('category_filter', actions.blocks.CategoryChooserBlock(label='Filter on category'))], label='Action list'))]),
        ),
        migrations.AlterField(
            model_name='categorypage',
            name='category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='category_page', to='actions.category', verbose_name='Category'),
        ),
    ]
