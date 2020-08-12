from django.utils.translation import gettext_lazy as _
from django.contrib.admin.widgets import AdminFileWidget
from wagtail.contrib.modeladmin.options import modeladmin_register

from wagtail.admin.edit_handlers import (
    FieldPanel, ObjectList
)
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.images.edit_handlers import ImageChooserPanel

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
    menu_order = 10
    exclude_from_explorer = False
    list_display = ('first_name', 'last_name')
    search_fields = ('first_name', 'last_name')

    edit_handler = PersonEditHandler([
        FieldPanel('first_name'),
        FieldPanel('last_name'),
        FieldPanel('email'),
        FieldPanel('title'),
        FieldPanel('image', widget=AvatarWidget),
    ], base_form_class=PersonForm)


modeladmin_register(PersonAdmin)
