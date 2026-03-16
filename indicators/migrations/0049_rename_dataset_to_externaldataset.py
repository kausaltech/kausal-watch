from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0048_indicatorgoaldatapoint_and_more'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='DatasetLicense',
            new_name='ExternalDatasetLicense',
        ),
        migrations.RenameModel(
            old_name='Dataset',
            new_name='ExternalDataset',
        ),
    ]
