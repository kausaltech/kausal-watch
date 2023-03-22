from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reversion', '0002_add_index_on_version_for_content_type_and_db'),
        ('actions', '0073_rename_report_tables'),
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='actionsnapshot',
            options={'get_latest_by': 'action_version__revision__date_created', 'verbose_name': 'action snapshot', 'verbose_name_plural': 'action snapshots'},
        ),
        migrations.AddField(
            model_name='actionsnapshot',
            name='created_explicitly',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='actionsnapshot',
            name='action_version',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_snapshots', to='reversion.version'),
        ),
        migrations.AlterField(
            model_name='actionsnapshot',
            name='report',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_snapshots', to='reports.report'),
        ),
        migrations.AlterField(
            model_name='report',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reports', to='reports.reporttype'),
        ),
        migrations.AlterField(
            model_name='reporttype',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='report_types', to='actions.plan'),
        ),
    ]
