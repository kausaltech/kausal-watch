# Generated by Django 3.2.13 on 2022-11-17 08:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0050_alter_category_i18n_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='lead_paragraph',
            field=models.TextField(blank=True, max_length=300, verbose_name='lead paragraph'),
        ),
        migrations.AlterField(
            model_name='commoncategory',
            name='lead_paragraph',
            field=models.TextField(blank=True, max_length=300, verbose_name='lead paragraph'),
        ),
    ]
