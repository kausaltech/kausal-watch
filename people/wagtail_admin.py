from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.contrib.admin.widgets import AdminFileWidget
from wagtail.contrib.modeladmin.options import modeladmin_register

from wagtail.admin.edit_handlers import (
    FieldPanel, ObjectList
)
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtailautocomplete.edit_handlers import AutocompletePanel

from admin_site.wagtail import AplansModelAdmin

from .models import Person


class AvatarWidget(AdminFileWidget):
    template_name = 'admin/avatar_widget.html'


class PersonForm(WagtailAdminModelForm):
    def save(self, commit=True):
        if 'image' in self.files:
            self.instance.image_cropping = None

        instance = super().save(commit)
        return instance


class PersonEditHandler(ObjectList):
    pass


class PersonAdmin(AplansModelAdmin):
    model = Person
    menu_icon = 'user'
    menu_label = _('People')
    menu_order = 10
    exclude_from_explorer = False
    search_fields = ('first_name', 'last_name', 'title')

    def get_list_display(self, request):
        def edit_url(obj):
            if self.permission_helper.user_can_edit_obj(request.user, obj):
                return self.url_helper.get_action_url('edit', obj.pk)
            else:
                return None

        def avatar(obj):
            avatar_url = obj.get_avatar_url(request, size='50x50')
            if not avatar_url:
                return ''
            img = format_html('<span class="avatar"><img src="{}" /></span>', avatar_url)
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, img)
            else:
                return img
        avatar.short_description = ''

        def first_name(obj):
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, obj.first_name)
            else:
                return obj.first_name
        first_name.short_description = _('first name')

        def last_name(obj):
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, obj.last_name)
            else:
                return obj.last_name
        last_name.short_description = _('last name')

        return (avatar, first_name, last_name, 'title', 'organization')

    edit_handler = PersonEditHandler([
        FieldPanel('first_name'),
        FieldPanel('last_name'),
        FieldPanel('email'),
        FieldPanel('title'),
        AutocompletePanel('organization'),
        FieldPanel('image', widget=AvatarWidget),
    ], base_form_class=PersonForm)


modeladmin_register(PersonAdmin)
