import re
from wagtail.embeds.finders.base import EmbedFinder


def get_thumbnail_url(provider, url):
    if provider == 'Plotly Chart Studio':
        return url.replace('.embed', '.png')
    return None


class GenericFinder(EmbedFinder):

    def __init__(self, **options):
        self.provider = options['provider']
        self.domain_whitelist = options['domain_whitelist']
        self.title = options['title']
        self.acceptable_url_re = re.compile(
            f'^https://([^/@:?.]+.)?({"|".join(self.domain_whitelist)})/.*'
        )

    def accept(self, url):
        """
        Returns True if this finder knows how to fetch an embed for the URL.

        This should not have any side effects (no requests to external servers)
        """
        return self.acceptable_url_re.match(url)

    def find_embed(self, url, max_width=None, max_height=None):
        """
        Takes a URL and max width and returns a dictionary of information about the
        content to be used for embedding it on the site.

        This is the part that may make requests to external APIs.
        """
        height = max_height if max_height is not None else 800
        width = max_width if max_width is not None else "100%"
        html = f'<iframe width="{width}" height="{height}" src="{url}"></iframe>'
        thumbnail_url = get_thumbnail_url(self.provider, url)
        result = {
            'title': self.title,
            # 'author_name': "Author name",
            'provider_name': self.provider,
            'type': 'rich',
            'width': None,
            'height': None,
            'html': html,
        }
        if thumbnail_url is not None:
            result['thumbnail_url'] = thumbnail_url
        return result
