from social_core.backends.azuread_tenant import AzureADTenantOAuth2
from .models import Client


class AzureADAuth(AzureADTenantOAuth2):
    name = 'azure_ad'
    AUTHORIZATION_URL = 'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize'
    DEFAULT_SCOPE = ['openid', 'profile']

    def authorization_url(self):
        client = Client.objects.for_request(self.strategy.request).first()
        if client is None or not client.azure_ad_tenant_id:
            tenant_id = 'common'
        else:
            tenant_id = client.azure_ad_tenant_id
        return self.AUTHORIZATION_URL.format(tenant_id=tenant_id)

    def get_user_id(self, details, response):
        """Use oid claim as unique id."""
        oid = response['oid']
        # Replace the pairwise 'sub' field with the oid to better play along
        # with helusers.
        response['sub'] = oid
        return oid

    def get_user_details(self, response):
        details = super().get_user_details(response)
        details['uuid'] = response.get('oid')
        return details
