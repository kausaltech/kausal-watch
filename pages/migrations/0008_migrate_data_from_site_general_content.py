# Generated by Django 3.1.5 on 2021-03-01 16:43

import actions.blocks
from django.db import migrations, models
import django.db.models.deletion
import indicators.blocks
import wagtail.core.blocks
import wagtail.core.fields
import wagtail.images.blocks


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0007_merge_20210204_1001'),
        ('wagtailcore', '0059_apply_collection_ordering'),
    ]

    operations = [
        migrations.AddField(
            model_name='planrootpage',
            name='hero_content',
            field=wagtail.core.fields.RichTextField(blank=True, verbose_name='hero content'),
        ),
        migrations.AddField(
            model_name='planrootpage',
            name='action_short_description',
            field=wagtail.core.fields.RichTextField(blank=True, verbose_name='Short description for what actions are'),
        ),
        migrations.AddField(
            model_name='planrootpage',
            name='indicator_short_description',
            field=wagtail.core.fields.RichTextField(blank=True, verbose_name='Short description for what indicators are'),
        ),
        migrations.AlterField(
            model_name='categorypage',
            name='body',
            field=wagtail.core.fields.StreamField([('text', wagtail.core.blocks.RichTextBlock(label='Text')), ('indicator_group', indicators.blocks.IndicatorGroupBlock()), ('category_list', wagtail.core.blocks.StructBlock([('style', wagtail.core.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table')]))], label='Category list')), ('action_list', wagtail.core.blocks.StructBlock([('category_filter', actions.blocks.CategoryChooserBlock(label='Filter on category'))], label='Action list'))]),
        ),
        migrations.AlterField(
            model_name='planrootpage',
            name='body',
            field=wagtail.core.fields.StreamField([('front_page_hero', wagtail.core.blocks.StructBlock([('layout', wagtail.core.blocks.ChoiceBlock(choices=[('big_image', 'Big image'), ('small_image', 'Small image')])), ('image', wagtail.images.blocks.ImageChooserBlock()), ('heading', wagtail.core.blocks.CharBlock(form_classname='full title', label='Heading')), ('lead', wagtail.core.blocks.RichTextBlock(label='Lead'))], label='Front page hero block')), ('category_list', wagtail.core.blocks.StructBlock([('style', wagtail.core.blocks.ChoiceBlock(choices=[('cards', 'Cards'), ('table', 'Table')]))], label='Category list')), ('indicator_group', indicators.blocks.IndicatorGroupBlock()), ('indicator_highlights', indicators.blocks.IndicatorHighlightsBlock(label='Indicator highlights')), ('indicator_showcase', wagtail.core.blocks.StructBlock([('title', wagtail.core.blocks.CharBlock(required=False)), ('body', wagtail.core.blocks.RichTextBlock(required=False)), ('indicator', indicators.blocks.IndicatorChooserBlock()), ('link_button', wagtail.core.blocks.StructBlock([('text', wagtail.core.blocks.CharBlock(required=False)), ('page', wagtail.core.blocks.PageChooserBlock(required=False))]))])), ('action_highlights', actions.blocks.ActionHighlightsBlock(label='Action highlights')), ('cards', wagtail.core.blocks.StructBlock([('heading', wagtail.core.blocks.CharBlock()), ('lead', wagtail.core.blocks.CharBlock(required=False)), ('cards', wagtail.core.blocks.ListBlock(wagtail.core.blocks.StructBlock([('image', wagtail.images.blocks.ImageChooserBlock(required=False)), ('heading', wagtail.core.blocks.CharBlock()), ('content', wagtail.core.blocks.CharBlock(required=False)), ('link', wagtail.core.blocks.CharBlock(required=False))])))]))]),
        ),
        migrations.CreateModel(
            name='ActionListPage',
            fields=[
                ('page_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wagtailcore.page')),
                ('i18n', models.JSONField(blank=True, null=True)),
                ('show_in_footer', models.BooleanField(default=False, help_text='Should the page be shown in the footer?', verbose_name='show in footer')),
                ('lead_content', wagtail.core.fields.RichTextField(blank=True, verbose_name='lead content')),
            ],
            options={
                'abstract': False,
            },
            bases=('wagtailcore.page',),
        ),
        migrations.CreateModel(
            name='ImpactGroupPage',
            fields=[
                ('page_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wagtailcore.page')),
                ('i18n', models.JSONField(blank=True, null=True)),
                ('show_in_footer', models.BooleanField(default=False, help_text='Should the page be shown in the footer?', verbose_name='show in footer')),
                ('lead_content', wagtail.core.fields.RichTextField(blank=True, verbose_name='lead content')),
            ],
            options={
                'abstract': False,
            },
            bases=('wagtailcore.page',),
        ),
        migrations.CreateModel(
            name='IndicatorListPage',
            fields=[
                ('page_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wagtailcore.page')),
                ('i18n', models.JSONField(blank=True, null=True)),
                ('show_in_footer', models.BooleanField(default=False, help_text='Should the page be shown in the footer?', verbose_name='show in footer')),
                ('lead_content', wagtail.core.fields.RichTextField(blank=True, verbose_name='lead content')),
            ],
            options={
                'abstract': False,
            },
            bases=('wagtailcore.page',),
        ),
    ]
