from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0174_alter_actionstatus_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='attributetypechoiceoption',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='active'),
        ),
    ]
