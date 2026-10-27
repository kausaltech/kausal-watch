from django.db import migrations, models


def rename_inactive_to_not_in_use(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    Plan.objects.filter(usage_status='inactive').update(usage_status='not_in_use')


def rename_not_in_use_to_inactive(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    Plan.objects.filter(usage_status='not_in_use').update(usage_status='inactive')


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0202_plandomain_order'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plan',
            name='usage_status',
            field=models.CharField(choices=[('customer_use', 'Customer use'), ('sales', 'Sales and demos'), ('development', 'Internal testing, training, development or other non-public use'), ('customer_offboarding', 'Offboarding in progress'), ('not_in_use', 'Not in use currently'), ('deprecated', 'Deprecated, should be deleted')], default='customer_use', help_text='If unsure, use the default value representing customer use. For statistical purposes specify what the plan will be used for in order to differentiate between plans actually in use by customers and those created for some other reason.', max_length=30, verbose_name='Usage status'),
        ),
        migrations.RunPython(rename_inactive_to_not_in_use, rename_not_in_use_to_inactive),
    ]
