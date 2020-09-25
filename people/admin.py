from django.contrib import admin
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _
from image_cropping import ImageCroppingMixin
from import_export import resources
from import_export.admin import ExportMixin
from import_export.fields import Field

from admin_site.admin import AplansExportMixin, AplansModelAdmin

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
            ('action', _('For an action')),
            ('indicator', _('For an indicator')),
            ('none', _('Not a contact person'))
        )

    def queryset(self, request, queryset):
        plan = request.user.get_active_admin_plan()
        queryset = queryset.prefetch_related(
            Prefetch('contact_for_actions', queryset=plan.actions.all(), to_attr='plan_contact_for_actions')
        )
        queryset = queryset.prefetch_related(
            Prefetch('contact_for_indicators', queryset=plan.indicators.all(), to_attr='plan_contact_for_indicators')
        )
        if self.value() is None:
            return queryset
        if self.value() == 'action':
            queryset = queryset.filter(contact_for_actions__in=plan.actions.all())
        elif self.value() == 'indicator':
            queryset = queryset.filter(contact_for_indicators__in=plan.indicators.all())
        else:
            queryset = queryset.exclude(contact_for_actions__in=plan.actions.all())\
                .exclude(contact_for_indicators__in=plan.indicators.all())
        return queryset.distinct()


@admin.register(Person)
class PersonAdmin(ImageCroppingMixin, AplansExportMixin, AplansModelAdmin):
    fields = (
        'first_name', 'last_name', 'email', 'title', 'postal_address',
        'organization', 'image', 'image_cropping'
    )
    search_fields = ('first_name', 'last_name',)
    autocomplete_fields = ('organization',)

    list_display = ('__str__', 'title', 'organization',)
    list_filter = (IsContactPersonFilter,)
    resource_class = PersonResource

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.available_for_plan(plan)

    def get_list_display(self, request):
        def contact_for_actions(obj):
            return '; '.join([str(act) for act in obj.plan_contact_for_actions])
        contact_for_actions.short_description = _('contact for actions')

        ret = super().get_list_display(request)
        return ret + (contact_for_actions,)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.download_avatar()
