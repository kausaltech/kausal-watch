# Generated by Django 3.1.5 on 2021-09-28 21:37

from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('images', '0001_initial'),
        ('admin_site', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='logo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.aplansimage'),
        ),
        migrations.AddField(
            model_name='adminhostname',
            name='client',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='admin_hostnames', to='admin_site.client'),
        ),
    ]
