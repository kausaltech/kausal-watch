# Generated by Django 3.2.13 on 2023-03-13 20:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0071_attributetype_plan_updates'),
    ]

    operations = [
        migrations.AddField(
            model_name='action',
            name='visibility',
            field=models.CharField(choices=[('draft', 'Draft'), ('public', 'Public')], default='public', max_length=20, verbose_name='visibility'),
        ),
    ]
