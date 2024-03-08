import re
from typing import Optional, Any
from collections import OrderedDict
from django.views.decorators.debug import sensitive_post_parameters

from django.views.generic.base import RedirectView
from django.contrib import messages
from django.urls import reverse


LANGUAGE_FIELD_NAME = 'ui_locales'


class RootRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        request = self.request
        if request.user.is_authenticated:
            url = reverse('wagtailadmin_home')
        else:
            url = reverse('graphql')
        return url


class WadminRedirectView(RedirectView):
    permanent = True

    def get_redirect_url(self, *args: Any, **kwargs: Any) -> Optional[str]:
        new_path = re.sub('^/wadmin', '/admin', self.request.get_full_path())
        return new_path


# FIXME: Copied from Wagtail's admin/views/account.py because I didn't find an easier way to remove ThemeSettingsPanel
# from the shown panels. Fix CSS issues in dark mode and remove this. See also aplans/urls.py
@sensitive_post_parameters()
def account(request):
    from django.contrib.auth import update_session_auth_hash
    from django.db import transaction
    from django.forms import Media
    from django.shortcuts import redirect
    from django.template.response import TemplateResponse
    from django.utils.translation import gettext as _, override

    from wagtail import hooks
    from wagtail.log_actions import log
    from wagtail.users.models import UserProfile

    from wagtail.admin.views.account import (
        NameEmailSettingsPanel, AvatarSettingsPanel, NotificationsSettingsPanel, LocaleSettingsPanel,
        ChangePasswordPanel
    )

    # Fetch the user and profile objects once and pass into each panel
    # We need to use the same instances for all forms so they don't overwrite each other
    user = request.user
    profile = UserProfile.get_for_user(user)

    # Panels
    panels = [
        NameEmailSettingsPanel(request, user, profile),
        AvatarSettingsPanel(request, user, profile),
        NotificationsSettingsPanel(request, user, profile),
        LocaleSettingsPanel(request, user, profile),
        # ThemeSettingsPanel(request, user, profile),  # commenting this out is the point of this whole mess
        ChangePasswordPanel(request, user, profile),
    ]
    for fn in hooks.get_hooks("register_account_settings_panel"):
        panel = fn(request, user, profile)
        if panel and panel.is_active():
            panels.append(panel)

    panels = [panel for panel in panels if panel.is_active()]

    # Get tabs and order them
    tabs = list({panel.tab for panel in panels})
    tabs.sort(key=lambda tab: tab.order)

    # Get dict of tabs to ordered panels
    panels_by_tab = OrderedDict([(tab, []) for tab in tabs])
    for panel in panels:
        panels_by_tab[panel.tab].append(panel)
    for tab, tab_panels in panels_by_tab.items():
        tab_panels.sort(key=lambda panel: panel.order)

    panel_forms = [panel.get_form() for panel in panels]

    if request.method == "POST":

        if all(form.is_valid() or not form.is_bound for form in panel_forms):
            with transaction.atomic():
                for form in panel_forms:
                    if form.is_bound:
                        form.save()

            log(user, "wagtail.edit")

            # Prevent a password change from logging this user out
            update_session_auth_hash(request, user)

            # Override the language when creating the success message
            # If the user has changed their language in this request, the message should
            # be in the new language, not the existing one
            with override(profile.get_preferred_language()):
                messages.success(
                    request, _("Your account settings have been changed successfully!")
                )

            return redirect("wagtailadmin_account")

    media = Media()
    for form in panel_forms:
        media += form.media

    # Menu items
    menu_items = []
    for fn in hooks.get_hooks("register_account_menu_item"):
        item = fn(request)
        if item:
            menu_items.append(item)

    return TemplateResponse(
        request,
        "wagtailadmin/account/account.html",
        {
            "panels_by_tab": panels_by_tab,
            "menu_items": menu_items,
            "media": media,
        },
    )

