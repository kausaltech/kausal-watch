# Generated by Django 3.2.16 on 2024-02-01 16:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documentation', '0001_add_documentation_page_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentationpage',
            name='css_style',
            field=models.CharField(blank=True, help_text='CSS style to be applied to the container of the body', max_length=1000, verbose_name='CSS style'),
        ),
    ]
