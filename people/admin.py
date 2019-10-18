from django.contrib import admin
from image_cropping import ImageCroppingMixin
from django.utils.translation import gettext_lazy as _
from .models import Person


@admin.register(Person)
class PersonAdmin(ImageCroppingMixin, admin.ModelAdmin):
    fields = ('first_name', 'last_name', 'email', 'title', 'organization', 'image', 'image_cropping')
    search_fields = ('first_name', 'last_name',)
    autocomplete_fields = ('organization',)

    list_display = ('__str__', 'title', 'organization',)

    def get_list_display(self, request):
        plan = request.user.get_active_admin_plan()

        def contact_for_actions(obj):
            return '; '.join([str(act) for act in obj.contact_for_actions.filter(plan=plan)])
        contact_for_actions.short_description = _('contact for actions')

        ret = super().get_list_display(request)
        return ret + (contact_for_actions,)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.download_avatar()
