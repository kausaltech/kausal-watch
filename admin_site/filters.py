from dal_admin_filters import AutocompleteFilter as DALFilter


class AutocompleteFilter(DALFilter):
    class Media:
        js = [
            'admin/js/vendor/select2/select2.full.js',
            'autocomplete_light/i18n/fi.js',
            'autocomplete_light/autocomplete_light.js',
            'autocomplete_light/select2.js',
            'dal_admin_filters/js/querystring.js',
        ]
        css = {
            'all': [
                'dal_admin_filters/css/select2.min.css',
                'autocomplete_light/select2.css',
                'dal_admin_filters/css/autocomplete-fix.css'
            ]
        }
