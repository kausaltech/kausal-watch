from dal import autocomplete
from django.contrib.admin.widgets import AdminFileWidget
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import FieldPanel, ObjectList
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.images.edit_handlers import ImageChooserPanel

from admin_site.wagtail import AplansModelAdmin
from users.models import User

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

    def get_queryset(self, request):
        plan = request.user.get_active_admin_plan()
        qs = super().get_queryset(request).available_for_plan(plan)
        return qs

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

        fields = [avatar, first_name, last_name, 'title', 'organization']

        def has_logged_in(obj):
            user = User.objects.filter(email__iexact=obj.email).first()
            if not user or not user.last_login:
                return False
            return True
        has_logged_in.short_description = _('has logged in')
        has_logged_in.boolean = True

        user = request.user
        plan = user.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            fields.append(has_logged_in)
            fields.append('participated_in_training')

        return fields

    basic_panels = [
        FieldPanel('first_name'),
        FieldPanel('last_name'),
        FieldPanel('email'),
        FieldPanel('title'),
        FieldPanel(
            'organization',
            widget=autocomplete.ModelSelect2(url='organization-autocomplete'),
        ),
        FieldPanel('image', widget=AvatarWidget),
    ]

    def get_edit_handler(self, instance, request):
        basic_panels = list(self.basic_panels)
        user = request.user
        plan = user.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            basic_panels.insert(3, FieldPanel('participated_in_training'))

        return PersonEditHandler(basic_panels, base_form_class=PersonForm)


modeladmin_register(PersonAdmin)
