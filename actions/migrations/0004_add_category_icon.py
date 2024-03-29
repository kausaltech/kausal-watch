# Generated by Django 3.1.5 on 2021-09-22 11:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0003_add_action_hide_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='action',
            name='image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.aplansimage', verbose_name='Image'),
        ),
        migrations.CreateModel(
            name='CategoryIcon',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.TextField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='icon', to='actions.category')),
            ],
        ),
    ]
