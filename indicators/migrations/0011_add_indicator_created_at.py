# Generated by Django 2.1.5 on 2019-02-05 15:16

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0010_remove_deprecated_fields'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='indicator',
            options={'ordering': ('-updated_at',), 'verbose_name': 'indicator', 'verbose_name_plural': 'indicators'},
        ),
        migrations.AlterModelOptions(
            name='indicatorlevel',
            options={'verbose_name': 'indicator levels', 'verbose_name_plural': 'indicator levels'},
        ),
        migrations.AddField(
            model_name='indicator',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='created at'),
            preserve_default=False,
        ),
    ]