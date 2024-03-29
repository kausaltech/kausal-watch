# Generated by Django 3.2.13 on 2022-06-27 22:24

from django.db import migrations
import django.db.models.deletion
import modelcluster.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0027_common_categories'),
    ]

    operations = [
        migrations.RenameField(
            model_name='commoncategoryicon',
            old_name='category',
            new_name='common_category',
        ),
        migrations.AlterUniqueTogether(
            name='commoncategoryicon',
            unique_together={('common_category', 'language')},
        ),
        migrations.AlterField(
            model_name='commoncategoryicon',
            name='common_category',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='icons', to='actions.commoncategory', verbose_name='category'),
        ),
    ]
