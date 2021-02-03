# Generated by Django 3.1.5 on 2021-02-03 08:46

from django.db import migrations, models
import wagtail.core.blocks
import wagtail.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0005_add_empty_page'),
    ]

    operations = [
        migrations.AddField(
            model_name='categorypage',
            name='show_in_footer',
            field=models.BooleanField(default=False, help_text='Should the page be shown in the footer?', verbose_name='show in footer'),
        ),
        migrations.AddField(
            model_name='emptypage',
            name='show_in_footer',
            field=models.BooleanField(default=False, help_text='Should the page be shown in the footer?', verbose_name='show in footer'),
        ),
        migrations.AddField(
            model_name='planrootpage',
            name='show_in_footer',
            field=models.BooleanField(default=False, help_text='Should the page be shown in the footer?', verbose_name='show in footer'),
        ),
        migrations.AddField(
            model_name='staticpage',
            name='show_in_footer',
            field=models.BooleanField(default=False, help_text='Should the page be shown in the footer?', verbose_name='show in footer'),
        ),
    ]
