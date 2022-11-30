import re
from wagtail.embeds.finders.base import EmbedFinder


class ArcGISFinder(EmbedFinder):
    ACCEPTABLE_URL_RE = re.compile(r'^https://([^/@:?.]+.)?arcgis.com/.*')

    def __init__(self, **options):
        pass

    def accept(self, url):
        """
        Returns True if this finder knows how to fetch an embed for the URL.

        This should not have any side effects (no requests to external servers)
        """
        return self.ACCEPTABLE_URL_RE.match(url)

    def find_embed(self, url, max_width=None):
        """
        Takes a URL and max width and returns a dictionary of information about the
        content to be used for embedding it on the site.

        This is the part that may make requests to external APIs.
        """
        return {
            'title': "Map",
            # 'author_name': "Author name",
            'provider_name': "ArcGIS",
            'type': 'rich',
            # 'thumbnail_url': "URL to thumbnail image",
            'width': None,
            'height': None,
            'html': f'<iframe width="100%" height="800" src="{url}"></iframe>',
        }
