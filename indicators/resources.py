import re
from collections import OrderedDict

from django.db.models import Max, Min
from django.utils.encoding import force_str
from django.utils.translation import gettext_lazy as _

from admin_site.admin import AplansResource
from import_export import fields, widgets

from .models import Indicator, IndicatorValue, IndicatorLevel, Unit


class YearField(fields.Field):
    def __init__(self, year, **kwargs):
        self.year = year
        super().__init__(widget=widgets.FloatWidget(), **kwargs)

    def get_value(self, obj):
        val_obj = obj._yearly_values.get(self.year)
        if not val_obj:
            return None
        else:
            return val_obj.value

    def save(self, obj, data, is_m2m=False):
        """
        If this field is not declared readonly, the object's attribute will
        be set to the value returned by :meth:`~import_export.fields.Field.clean`.
        """
        if self.readonly:
            return

        existing = obj._yearly_values.get(self.year)
        cleaned = self.clean(data)
        if cleaned is None:
            if existing is not None:
                existing.delete()
                del obj._yearly_values[self.year]
        else:
            if existing:
                if existing.value != cleaned:
                    existing.value = cleaned
                    existing.save(update_fields=['value'])
            else:
                ret = obj.values.create(indicator=obj, date='%s-12-31' % self.year, value=cleaned)
                obj._yearly_values[self.year] = ret


class UnitWidget(widgets.ForeignKeyWidget):
    def get_queryset(self, value, row, *args, **kwargs):
        return super().get_queryset(value, row, *args, **kwargs)

    def clean(self, value, row=None, *args, **kwargs):
        qs = super().get_queryset(value, row, *args, **kwargs)
        unit = qs.filter(name=value).first()
        if not unit:
            unit = qs.filter(short_name=value).first()
        if not unit:
            raise ValueError("Unit '%s' does not exist" % value)
        return unit


class IndicatorResource(AplansResource):
    unit = fields.Field(
        column_name='unit',
        attribute='unit',
        widget=UnitWidget(Unit, 'name'),
    )

    def get_fields(self, **kwargs):
        out = super().get_fields(**kwargs)

        if not hasattr(self, 'yearly_fields'):
            fields = []
            for year in range(self.min_year, self.max_year + 1):
                fields.append(YearField(attribute=str(year), column_name=str(year), year=year))
            self.yearly_fields = fields
        return out + self.yearly_fields

    def get_user_visible_fields(self):
        if not hasattr(self, 'min_year'):
            return super().get_fields()
        else:
            return self.get_fields()

    def get_field_name(self, field):
        if isinstance(field, YearField):
            return str(field.year)
        else:
            return super().get_field_name(field)

    def _set_yearly_values(self, obj):
        assert obj.time_resolution == 'year'

        # Use only dimensionless values in export
        obj._yearly_values = {x.date.year: x for x in obj.values.filter(categories__isnull=True)}

    def export_resource(self, obj):
        self._set_yearly_values(obj)
        return super().export_resource(obj)

    def export(self, queryset=None, *args, **kwargs):
        if queryset is not None:
            queryset = queryset.filter(time_resolution='year')
        return super().export(queryset, *args, **kwargs)

    def before_export(self, queryset, *args, **kwargs):
        out = IndicatorValue.objects.filter(indicator__in=queryset).aggregate(Min('date'), Max('date'))
        self.min_year = out['date__min'].year
        self.max_year = out['date__max'].year

    def import_field(self, field, obj, data, is_m2m=False):
        # If the indicator exists, do not allow changing its metadata
        if obj.pk:
            if not isinstance(field, YearField):
                return
        super().import_field(field, obj, data, is_m2m)

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        def convert_header(header):
            if isinstance(header, float):
                header = int(header)
            return force_str(header)

        dataset.headers = [convert_header(x) for x in dataset.headers]

    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        user = self.request.user
        if new:
            plan = user.get_active_admin_plan()
            if not user.can_create_indicator(plan):
                raise Exception(_("Creating new indicators is not allowed"))
            instance.organization = plan.organization
        else:
            user = self.request.user
            if not user.can_modify_indicator(instance):
                raise Exception(_("Permission denied"))

            if instance.latest_value:
                instance.latest_value = None
                instance.save(update_fields=['latest_value'])

        self._set_yearly_values(instance)

    def after_save_instance(self, instance, using_transactions, dry_run):
        if dry_run:
            return

        instance.set_latest_value()
        user = self.request.user
        plan = user.get_active_admin_plan()
        if not instance.levels.filter(plan=plan).exists():
            IndicatorLevel.objects.create(indicator=instance, plan=plan, level='tactical')

    def import_data_inner(self, dataset, *args, **kwargs):
        years = []
        for header in dataset.headers:
            if isinstance(header, (int, float)):
                if header >= 1900 and header < 2100:
                    years.append(int(header))
            elif re.match(r'[12][0-9]{3}', header):
                years.append(int(header))
        self.min_year = min(years)
        self.max_year = max(years)
        return super().import_data_inner(dataset, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(time_resolution='year')

    class Meta:
        model = Indicator
        fields = ('id', 'name', 'unit')
        import_id_fields = ('id',)
        skip_unchanged = True
