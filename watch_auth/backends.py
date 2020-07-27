from social_core.backends.azuread_tenant import AzureADTenantOAuth2


class AzureADAuth(AzureADTenantOAuth2):
    name = 'azure_ad'

    def get_user_id(self, details, response):
        """Use subject (sub) claim as unique id."""
        print(details)
        print(response)
        return response.get('sub')
