from django.db import migrations, models


def migrate_data(apps, schema_editor):
    PlanFeatures = apps.get_model('actions', 'PlanFeatures')
    PlanFeatures.objects.filter(public_contact_persons=True).update(contact_persons_public_data='all')
    PlanFeatures.objects.filter(public_contact_persons=False).update(contact_persons_public_data='none')


def reverse_migrate_data(apps, schema_editor):
    PlanFeatures = apps.get_model('actions', 'PlanFeatures')
    PlanFeatures.objects.filter(contact_persons_public_data='all').update(public_contact_persons=True)
    PlanFeatures.objects.exclude(contact_persons_public_data='all').update(public_contact_persons=False)


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0085_attribute_type_permissions_sane_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='planfeatures',
            name='contact_persons_public_data',
            field=models.CharField(choices=[('none', 'Do not show contact persons publicly'), ('name', 'Show only name, role and affiliation'), ('all', 'Show all information')], default='all', help_text='Choose which information about contact persons is visible in the public UI', max_length=50, verbose_name='Publicly visible data about contact persons'),
        ),
        migrations.RunPython(migrate_data, reverse_migrate_data),
        migrations.RemoveField(
            model_name='planfeatures',
            name='public_contact_persons',
        ),
    ]
