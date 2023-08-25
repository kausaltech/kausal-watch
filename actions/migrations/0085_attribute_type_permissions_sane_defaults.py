from django.db import migrations, models


def migrate_data(apps, schema_editor):
    AttributeType = apps.get_model('actions', 'AttributeType')
    AttributeType.objects.filter(instances_editable_by='').update(instances_editable_by='authenticated')
    AttributeType.objects.filter(instances_visible_for='').update(instances_visible_for='public')
    CategoryType = apps.get_model('actions', 'CategoryType')
    AttributeType.objects.filter(instances_editable_by='').update(instances_editable_by='authenticated')


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0084_attribute_type_visibility'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attributetype',
            name='instances_editable_by',
            field=models.CharField(choices=[('authenticated', 'Authenticated users'), ('contact_persons', 'Contact persons'), ('plan_admins', 'Plan admins'), ('not_editable', 'Not editable')], default='authenticated', max_length=50, verbose_name='Edit rights'),
        ),
        migrations.AlterField(
            model_name='attributetype',
            name='instances_visible_for',
            field=models.CharField(choices=[('public', 'Public'), ('authenticated', 'Authenticated users'), ('contact_persons', 'Contact persons'), ('plan_admins', 'Plan admins')], default='public', max_length=50, verbose_name='Visibility'),
        ),
        migrations.AlterField(
            model_name='categorytype',
            name='instances_editable_by',
            field=models.CharField(choices=[('authenticated', 'Authenticated users'), ('contact_persons', 'Contact persons'), ('plan_admins', 'Plan admins'), ('not_editable', 'Not editable')], default='authenticated', max_length=50, verbose_name='Edit rights'),
        ),
        migrations.RunPython(migrate_data),
    ]
