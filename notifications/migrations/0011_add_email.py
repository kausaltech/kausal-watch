# Generated by Django 3.2.13 on 2023-02-22 17:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0004_add_created_by_field'),
        ('notifications', '0010_notification_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationtemplate',
            name='custom_email',
            field=models.EmailField(blank=True, help_text='Email address used when "send to custom email address" is checked', max_length=254, verbose_name='custom email address'),
        ),
        migrations.AddField(
            model_name='notificationtemplate',
            name='send_to_contact_persons',
            field=models.BooleanField(default=False, verbose_name='send to contact persons'),
        ),
        migrations.AddField(
            model_name='notificationtemplate',
            name='send_to_custom_email',
            field=models.BooleanField(default=False, verbose_name='send to custom email address'),
        ),
        migrations.AddField(
            model_name='notificationtemplate',
            name='send_to_plan_admins',
            field=models.BooleanField(default=True, verbose_name='send to plan admins'),
        ),
        migrations.AddConstraint(
            model_name='notificationtemplate',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('custom_email', ''), ('send_to_custom_email', False)), models.Q(models.Q(('custom_email', ''), _negated=True), ('send_to_custom_email', True)), _connector='OR'), name='custom_email_iff_send_to_custom_email'),
        ),
        migrations.AddField(
            model_name='sentnotification',
            name='email',
            field=models.EmailField(blank=True, help_text='Set if the notification was sent to an email address instead of a person', max_length=254),
        ),
        migrations.AlterField(
            model_name='sentnotification',
            name='person',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='people.person'),
        ),
        migrations.AddConstraint(
            model_name='sentnotification',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('person__isnull', True), models.Q(('email', ''), _negated=True)), models.Q(('person__isnull', False), ('email', '')), _connector='OR'), name='person_xor_email'),
        ),
    ]
