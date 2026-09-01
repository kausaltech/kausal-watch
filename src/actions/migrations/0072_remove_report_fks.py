from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0071_actionsnapshot'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations = [
                migrations.RemoveField(
                    model_name='actionsnapshot',
                    name='action_version',
                ),
                migrations.RemoveField(
                    model_name='actionsnapshot',
                    name='report',
                ),
                migrations.RemoveField(
                    model_name='report',
                    name='type',
                ),
                migrations.RemoveField(
                    model_name='reporttype',
                    name='plan',
                ),
            ],
        ),
        migrations.AlterModelOptions(
            name='attributetype',
            options={'ordering': ('scope_content_type', 'scope_id', 'order'), 'verbose_name': 'attribute type', 'verbose_name_plural': 'attribute types'},
        ),
    ]
