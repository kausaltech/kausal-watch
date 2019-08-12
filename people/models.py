from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


User = get_user_model()


class Person(models.Model):
    first_name = models.CharField(max_length=100, verbose_name=_('first name'))
    last_name = models.CharField(max_length=100, verbose_name=_('last name'))
    email = models.EmailField(null=True, blank=True, verbose_name=_('email address'))
    organization = models.ForeignKey(
        'django_orghierarchy.Organization', null=True, blank=True, related_name='people',
        on_delete=models.SET_NULL, verbose_name=_('organization'),
        help_text=_('Set if this person is part of an organization')
    )
    user = models.OneToOneField(
        User, null=True, blank=True, related_name='person', on_delete=models.SET_NULL,
        verbose_name=_('user'), help_text=_('Set if the person has an user account')
    )

    class Meta:
        verbose_name = _('person')
        verbose_name_plural = _('people')
        ordering = ('last_name', 'first_name')

    def validate_unique(self, exclude=None):
        super().validate_unique(exclude)
        if self.email:
            qs = Person.objects.filter(email__iexact=self.email)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({
                'email': _('Person with this email already exists')
            })

    def get_avatar_url(self):
        if not self.email:
            return None
        if self.email.endswith('@hel.fi'):
            return 'https://api.hel.fi/avatar/%s?s=240' % self.email
        return None

    def __str__(self):
        return "%s %s" % (self.first_name, self.last_name)
