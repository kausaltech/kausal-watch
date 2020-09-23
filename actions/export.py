from django.utils.translation import ugettext_lazy as _
from import_export.fields import Field

from admin_site.admin import AplansResource

from .models import Action


class ActionResource(AplansResource):
    identifier = Field(attribute='identifier', column_name=_('identifier'))
    name = Field(attribute='name', column_name=_('name'))
    impact = Field(attribute='impact__name', column_name=_('impact'))
    status = Field(attribute='status__name', column_name=_('status'))
    progress_indicators = Field(attribute='related_indicators', column_name=_('progress indicators'))
    indicators = Field(attribute='related_indicators', column_name=_('other indicators'))
    contact_persons = Field(attribute='contact_persons', column_name=_('contact persons'))

    class Meta:
        model = Action
        fields = (
            'identifier', 'name', 'impact', 'status', 'progress_indicators', 'indicators', 'contact_persons',
        )
        export_order = fields

    def _dehydrate_indicators(self, obj, qs):
        plan = self.request.user.get_active_admin_plan()
        return '; '.join(['%s [%s]' % (str(ai.indicator), ai.indicator.get_level_for_plan(plan)) for ai in qs])

    def dehydrate_progress_indicators(self, obj):
        qs = obj.related_indicators.filter(indicates_action_progress=True)
        return self._dehydrate_indicators(obj, qs)

    def dehydrate_indicators(self, obj):
        qs = obj.related_indicators.filter(indicates_action_progress=False)
        return self._dehydrate_indicators(obj, qs)

    def dehydrate_contact_persons(self, obj):
        return '; '.join(['%s' % str(cp.person) for cp in obj.contact_persons.all()])
