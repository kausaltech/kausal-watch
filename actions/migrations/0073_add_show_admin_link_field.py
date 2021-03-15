# Generated by Django 3.1.5 on 2021-03-15 09:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_orghierarchy', '0010_update_tree_fields'),
        ('actions', '0072_remove_unique_together_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='action',
            name='responsible_organizations',
            field=models.ManyToManyField(blank=True, related_name='responsible_for_actions', through='actions.ActionResponsibleParty', to='django_orghierarchy.Organization', verbose_name='responsible organizations'),
        ),
        migrations.AddField(
            model_name='plan',
            name='show_admin_link',
            field=models.BooleanField(default=False, help_text='Should the public website contain a link to the admin login?', verbose_name='show admin link'),
        ),
    ]
