from django.contrib import admin
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _
from image_cropping import ImageCroppingMixin
from import_export import resources
from import_export.admin import ExportMixin
from import_export.fields import Field

from admin_site.admin import AplansModelAdmin
from .models import Person


class PersonResource(resources.ModelResource):
    contact_for_actions = Field()

    class Meta:
        model = Person
        fields = (
            'last_name', 'first_name', 'email', 'title', 'organization__distinct_name',
            'contact_for_actions', 'postal_address'
        )
        export_order = fields

    def __init__(self, request):
        self.request = request
        super().__init__()

    def dehydrate_contact_for_actions(self, obj):
        plan = self.request.user.get_active_admin_plan()
        return '; '.join([str(act) for act in obj.contact_for_actions.filter(plan=plan)])


class IsContactPersonFilter(admin.SimpleListFilter):
    title = _('Is contact person')
    parameter_name = 'contact_person'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No'))
        )

    def queryset(self, request, queryset):
        plan = request.user.get_active_admin_plan()
        queryset = queryset.prefetch_related(
            Prefetch('contact_for_actions', queryset=plan.actions.all(), to_attr='plan_contact_for_actions')
        )
        if self.value() is None:
            return queryset
        if self.value() == 'yes':
            queryset = queryset.filter(contact_for_actions__in=plan.actions.all())
        else:
            queryset = queryset.exclude(contact_for_actions__in=plan.actions.all())
        return queryset.distinct()


class ExportMixinWithRequest(ExportMixin):
    def get_resource_kwargs(self, request, *args, **kwargs):
        return dict(request=request)


@admin.register(Person)
class PersonAdmin(ImageCroppingMixin, ExportMixinWithRequest, AplansModelAdmin):
    fields = (
        'first_name', 'last_name', 'email', 'title', 'postal_address',
        'organization', 'image', 'image_cropping'
    )
    search_fields = ('first_name', 'last_name',)
    autocomplete_fields = ('organization',)

    list_display = ('__str__', 'title', 'organization',)
    list_filter = (IsContactPersonFilter,)
    resource_class = PersonResource

    def get_list_display(self, request):
        def contact_for_actions(obj):
            return '; '.join([str(act) for act in obj.plan_contact_for_actions])
        contact_for_actions.short_description = _('contact for actions')

        ret = super().get_list_display(request)
        return ret + (contact_for_actions,)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.download_avatar()
