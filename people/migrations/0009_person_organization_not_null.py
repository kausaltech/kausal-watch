# Generated by Django 3.1.6 on 2021-02-22 18:15

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('django_orghierarchy', '0010_update_tree_fields'),
        ('people', '0008_add_participated_in_training_flag'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='organization',
            field=models.ForeignKey(help_text="What is this person's organization", on_delete=django.db.models.deletion.PROTECT, related_name='people', to='django_orghierarchy.organization', verbose_name='organization'),
        ),
        migrations.AlterField(
            model_name='person',
            name='participated_in_training',
            field=models.BooleanField(default=False, help_text='Set to keep track who have attended training sessions', null=True, verbose_name='participated in training'),
        ),
    ]
