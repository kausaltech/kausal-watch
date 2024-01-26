# Generated by Django 3.2.16 on 2024-01-26 14:44

import aplans.utils
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0028_add_embed_full_width_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='actionlistpage',
            name='action_date_format',
            field=aplans.utils.DateFormatField(choices=[('FULL', 'Day, month and year (1.11.2020)'), ('MONTH_YEAR', 'Month and year (11.2020)'), ('YEAR', 'Year (2020)')], default='FULL', help_text='Default format of action start and end dates shown in the public UI.', max_length=16, verbose_name='Action date format'),
        ),
        migrations.AddField(
            model_name='actionlistpage',
            name='task_date_format',
            field=aplans.utils.DateFormatField(choices=[('FULL', 'Day, month and year (1.11.2020)'), ('MONTH_YEAR', 'Month and year (11.2020)'), ('YEAR', 'Year (2020)')], default='FULL', help_text='Default format of action task due dates shown in the public UI.', max_length=16, verbose_name='Task due date format'),
        ),
    ]
