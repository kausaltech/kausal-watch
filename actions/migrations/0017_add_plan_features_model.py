# Generated by Django 3.2.12 on 2022-03-10 08:06

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0016_alter_action_i18n'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanFeatures',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allow_images_for_actions', models.BooleanField(default=True, help_text='Should custom images for individual actions be allowed', verbose_name='allow images for actions')),
                ('show_admin_link', models.BooleanField(default=False, help_text='Should the public website contain a link to the admin login?', verbose_name='show admin link')),
                ('public_contact_persons', models.BooleanField(default=True, help_text='Set if the contact persons should be visible in the public UI', verbose_name='Contact persons private')),
                ('has_action_identifiers', models.BooleanField(default=True, help_text='Set if the plan uses meaningful action identifiers', verbose_name='Hide action identifiers')),
                ('has_action_official_name', models.BooleanField(default=False, help_text='Set if the plan uses the official name field', verbose_name='Hide official name field')),
                ('has_action_lead_paragraph', models.BooleanField(default=True, help_text='Set if the plan uses the lead paragraph field', verbose_name='Hide lead paragraph')),
                ('has_action_primary_orgs', models.BooleanField(default=False, help_text='Set if actions have a clear primary organisation (such as multi-city plans)', verbose_name='Has primary organisations for actions')),
                ('enable_search', models.BooleanField(default=True, help_text='Enable site-wide search functionality', null=True, verbose_name='Enable site search')),
                ('plan', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='features', to='actions.plan')),
            ],
            options={
                'verbose_name': 'plan feature',
                'verbose_name_plural': 'plan features',
            },
        ),
    ]
