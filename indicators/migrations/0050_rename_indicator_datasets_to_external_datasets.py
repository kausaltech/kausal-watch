from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0049_rename_dataset_to_externaldataset'),
    ]

    operations = [
        migrations.RenameField(
            model_name='indicator',
            old_name='datasets',
            new_name='external_datasets',
        ),
    ]
