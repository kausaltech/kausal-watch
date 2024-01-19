# Generated by Django 3.2.16 on 2024-01-19 15:42

from django.db import migrations, models
import django.db.models.deletion
import wagtail.blocks
import wagtail.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('wagtailcore', '0089_log_entry_data_json_null_to_object'),
        ('actions', '0101_add_documentation_page_types'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentationPage',
            fields=[
                ('page_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wagtailcore.page')),
                ('body', wagtail.fields.StreamField([('text', wagtail.blocks.RichTextBlock(label='Text'))], blank=True, use_json_field=True)),
            ],
            options={
                'verbose_name': 'Documentation page',
                'verbose_name_plural': 'Documentation pages',
            },
            bases=('wagtailcore.page',),
        ),
        migrations.CreateModel(
            name='DocumentationRootPage',
            fields=[
                ('page_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='wagtailcore.page')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documentation_root_pages', to='actions.plan')),
            ],
            options={
                'abstract': False,
            },
            bases=('wagtailcore.page',),
        ),
    ]
