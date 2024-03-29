# Generated by Django 3.2.13 on 2022-06-29 10:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wagtailcore', '0066_collection_management_permissions'),
        ('actions', '0030_attribute_type_numeric_unit'),
    ]

    operations = [
        migrations.AddField(
            model_name='commoncategorytype',
            name='collection',
            field=models.OneToOneField(editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='common_category_type', to='wagtailcore.collection'),
        ),
        migrations.AddField(
            model_name='commoncategorytype',
            name='has_collection',
            field=models.BooleanField(default=False, help_text='Set if this category type should have its own collection for images', verbose_name='has a collection'),
        ),
        migrations.AlterField(
            model_name='action',
            name='related_actions',
            field=models.ManyToManyField(blank=True, related_name='_actions_action_related_actions_+', to='actions.Action', verbose_name='related actions'),
        ),
    ]
