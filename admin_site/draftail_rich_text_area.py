import re
from copy import deepcopy
from django.utils.translation import gettext
from wagtail.admin.rich_text import DraftailRichTextArea

# Workaround until https://github.com/wagtail/wagtail/pull/11075 is merged
class DraftailRichTextAreaWithFixedTranslations(DraftailRichTextArea):
    def get_context(self, name, value, attrs):
        old_options = self.options
        self.options = deepcopy(old_options)
        for option in self.options.values():
            if isinstance(option, list):
                for item in option:
                    if isinstance(item, dict) and 'description' in item and isinstance(item['description'], str):
                        # Use gettext on the description; but if it's "Heading <int>", we need to do some extra work
                        match = re.fullmatch(r'Heading (\d+)', item['description'])
                        if match:
                            item['description'] = gettext('Heading %(level)d') % {'level': int(match.group(1))}
                        else:
                            item['description'] = gettext(item['description'])
        context = super().get_context(name, value, attrs)
        self.options = old_options
        return context
