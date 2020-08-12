# Generated by Django 3.0.9 on 2020-08-10 07:17

from django.db import migrations, models
import django.db.models.deletion
import modeltrans.fields
import wagtail.core.blocks
import wagtail.core.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('wagtailcore', '0045_assign_unlock_grouppagepermission'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanRootPage',
            fields=[
                ('page_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wagtailcore.Page')),
                ('i18n', modeltrans.fields.TranslationField(fields=('title', 'slug', 'url_path'), required_languages=(), virtual_fields=True)),
            ],
            options={
                'abstract': False,
            },
            bases=('wagtailcore.page',),
        ),
        migrations.CreateModel(
            name='StaticPage',
            fields=[
                ('page_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wagtailcore.Page')),
                ('i18n', modeltrans.fields.TranslationField(fields=('title', 'slug', 'url_path'), required_languages=(), virtual_fields=True)),
                ('body', wagtail.core.fields.StreamField([('heading', wagtail.core.blocks.CharBlock(classname='full title')), ('paragraph', wagtail.core.blocks.RichTextBlock())])),
            ],
            options={
                'abstract': False,
            },
            bases=('wagtailcore.page',),
        ),
    ]