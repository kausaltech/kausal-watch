from django.utils.translation import ugettext_lazy as _
from import_export import resources
from import_export.fields import Field

from admin_site.admin import AplansResource

from .models import Action


class ActionResource(AplansResource):
    identifier = Field(attribute='identifier', column_name=_('identifier'))
    name = Field(attribute='name', column_name=_('name'))
    impact = Field(attribute='impact__name', column_name=_('impact'))
    status = Field(attribute='status__name', column_name=_('status'))
    indicators = Field(attribute='indicators', column_name=_('indicators'))
    contact_persons = Field(attribute='contact_persons', column_name=_('contact persons'))

    class Meta:
        model = Action
        fields = (
            'identifier', 'name', 'impact', 'status', 'indicators', 'contact_persons',
        )
        export_order = fields

    def dehydrate_indicators(self, obj):
        plan = self.request.user.get_active_admin_plan()
        return '; '.join(['%s [%s]' % (str(indicator), indicator.get_level_for_plan(plan)) for indicator in obj.indicators.all()])

    def dehydrate_contact_persons(self, obj):
        return '; '.join(['%s' % str(cp.person) for cp in obj.contact_persons.all()])
