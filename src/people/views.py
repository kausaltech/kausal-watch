from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.admin.utils import unquote
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.functional import cached_property
from django.utils.http import urlsafe_base64_encode
from django.utils.text import capfirst
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.forms.auth import PasswordResetForm

from people.models import Person

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.utils.functional import _StrOrPromise as StrOrPromise

    from users.models import User


class PersonActionView(TemplateView):
    """A confirmation page for an action on one person."""

    request: HttpRequest
    page_title: StrOrPromise = ''
    page_subtitle: StrOrPromise = ''
    header_icon = 'user'
    target_person: Person
    target_person_pk: str

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.target_person_pk = unquote(str(kwargs['instance_pk']))
        self.target_person = get_object_or_404(Person, pk=self.target_person_pk)

    def check_action_permitted(self, user) -> bool:
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        if not self.check_action_permitted(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_page_title(self):
        return self.page_title or capfirst(Person._meta.verbose_name_plural)

    def get_page_subtitle(self):
        return self.page_subtitle

    @cached_property
    def index_url(self):
        return reverse('wagtailsnippets_people_person:list')


class ResetPasswordView(PersonActionView):
    page_title = gettext_lazy('Reset password')
    template_name = 'aplans/confirmation.html'

    def check_action_permitted(self, user):
        plan = user.get_active_admin_plan()
        user_is_admin = user.is_general_admin_for_plan(plan)
        target_user = self.target_person.user
        assert target_user is not None
        target_is_admin_of_any_plan = target_user.is_general_admin_for_plan()
        # Better safe than sorry...
        target_in_same_plan = Person.objects.qs.available_for_plan(plan).filter(pk=self.target_person_pk).exists()
        return user_is_admin and target_in_same_plan and not target_user.is_superuser and not target_is_admin_of_any_plan

    def get_meta_title(self):
        msg = _('Confirm sending password reset link to %(person)s')
        return msg % {'person': self.target_person}

    def confirmation_message(self):
        msg = _('Do you really want to send a password reset link to %(person)s?')
        return msg % {'person': self.target_person}

    def reset_password(self):
        # Does mostly the same as Wagtail's wagtail.admin.views.PasswordResetView
        target_user = self.target_person.user
        assert target_user is not None
        form = PasswordResetForm({
            'email': target_user.email,
        })
        assert form.is_valid()
        save_kwargs = {
            'use_https': self.request.is_secure(),
            'email_template_name': 'wagtailadmin/account/password_reset/email.txt',
            'subject_template_name': 'wagtailadmin/account/password_reset/email_subject.txt',
            'request': self.request,
        }
        form.save(**save_kwargs)  # pyright: ignore[reportArgumentType]

    def make_reset_url(self):
        # cf. wagtail.contrib.auth.forms.PasswordResetForm.save()
        target_user = self.target_person.user
        assert target_user is not None
        reset_token = default_token_generator.make_token(target_user)
        uid = urlsafe_base64_encode(force_bytes(target_user.pk))
        kwargs = {'uidb64': uid, 'token': reset_token}
        reset_path = reverse('wagtailadmin_password_reset_confirm', kwargs=kwargs)
        return f'{settings.ADMIN_BASE_URL}{reset_path}'

    def post(self, request, *args, **kwargs):
        try:
            self.reset_password()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        success_msg = _('An email has been sent to %(person)s with a link to reset their password.')
        info_msg = _('If the email does not arrive, you can send them the following link: %(url)s')
        warning_msg = _(
            'Please take great care that nobody except %(person)s gets access to the link. For additional security, '
            'the link will expire in %(days_until_expiration)s days.',
        )
        messages.success(request, success_msg % {'person': self.target_person})
        messages.info(request, info_msg % {'url': self.make_reset_url()})
        messages.warning(
            request,
            warning_msg
            % {
                'person': self.target_person,
                'days_until_expiration': int(settings.PASSWORD_RESET_TIMEOUT / (60 * 60 * 24)),
            },
        )
        return redirect(self.index_url)


class ImpersonateUserView(PersonActionView):
    page_title = gettext_lazy('View as user')
    template_name = 'people/view_as_user.html'
    post_url = reverse_lazy('hijack:acquire')

    def check_action_permitted(self, user: User) -> bool:
        target_user = self.target_person.user
        if target_user is None:
            return False

        impersonate_themselves = user.pk == target_user.pk
        target_is_active = target_user.is_active

        return user.is_superuser and not impersonate_themselves and target_is_active

    def get_meta_title(self):
        msg = _('Confirm viewing the site as user %(person)s')
        return msg % {'person': self.target_person}

    def confirmation_message(self):
        msg = _('Do you really want to view the site as %(person)s?')
        return msg % {'person': self.target_person}
