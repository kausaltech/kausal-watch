# Generated by Django 3.2.13 on 2022-08-08 17:42

from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields
import wagtail.fields


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0004_remove_i18n_from_notifications'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='contentblock',
            options={'ordering': ('base', 'identifier'), 'verbose_name': 'content block', 'verbose_name_plural': 'content blocks'},
        ),
        migrations.AlterModelOptions(
            name='notificationtemplate',
            options={'ordering': ('type', 'subject'), 'verbose_name': 'notification template', 'verbose_name_plural': 'notification templates'},
        ),
        migrations.AlterField(
            model_name='basetemplate',
            name='font_css_url',
            field=models.URLField(blank=True, help_text='Leave empty unless custom font required by customer', null=True, verbose_name='Font CSS style URL'),
        ),
        migrations.AlterField(
            model_name='basetemplate',
            name='font_family',
            field=models.CharField(blank=True, help_text='Leave empty unless custom font required by customer', max_length=200, null=True, verbose_name='Font family'),
        ),
        migrations.AlterField(
            model_name='contentblock',
            name='base',
            field=modelcluster.fields.ParentalKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='content_blocks', to='notifications.basetemplate'),
        ),
        migrations.AlterField(
            model_name='contentblock',
            name='content',
            field=wagtail.fields.RichTextField(help_text='HTML content for the block', verbose_name='content'),
        ),
        migrations.AlterField(
            model_name='notificationtemplate',
            name='base',
            field=modelcluster.fields.ParentalKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='templates', to='notifications.basetemplate'),
        ),
    ]
