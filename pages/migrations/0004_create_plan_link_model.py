# Generated by Django 3.2.13 on 2022-06-20 14:22

import actions.blocks
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import indicators.blocks
import modelcluster.fields
import modeltrans.fields
import wagtail.blocks
import wagtail.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0027_common_categories'),
        ('pages', '0003_category_type_page'),
    ]

    operations = [
        migrations.AlterField(
            model_name='categorypage',
            name='body',
            field=wagtail.fields.StreamField([('text', wagtail.blocks.RichTextBlock(label='Text')), ('indicator_group', indicators.blocks.IndicatorGroupBlock()), ('related_indicators', indicators.blocks.RelatedIndicatorsBlock()), ('category_list', wagtail.blocks.StructBlock([('heading', wagtail.blocks.CharBlock(form_classname='full title', label='Heading', required=False)), ('lead', wagtail.blocks.RichTextBlock(label='Lead', required=False)), ('style', wagtail.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table'), ('treemap', 'Tree map')]))], label='Category list')), ('action_list', wagtail.blocks.StructBlock([('category_filter', actions.blocks.CategoryChooserBlock(label='Filter on category'))], label='Action list'))], blank=True, null=True),
        ),
        migrations.CreateModel(
            name='PlanLink',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('url', models.URLField(max_length=400, validators=[django.core.validators.URLValidator(('http', 'https'))], verbose_name='URL')),
                ('title', models.CharField(blank=True, max_length=254, verbose_name='title')),
                ('i18n', modeltrans.fields.TranslationField(fields=['title', 'url'], required_languages=(), virtual_fields=True)),
                ('plan', modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='links', to='actions.plan', verbose_name='plan')),
            ],
            options={
                'verbose_name': 'plan link',
                'verbose_name_plural': 'plan links',
                'ordering': ['plan', 'order'],
                'index_together': {('plan', 'order')},
            },
        ),
    ]
