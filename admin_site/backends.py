from social_core.backends.azuread_tenant import AzureADTenantOAuth2
from social_core.backends.open_id_connect import OpenIdConnectAuth
from django.conf import settings

class AzureADAuth(AzureADTenantOAuth2):
    name = 'azure_ad'
    DEFAULT_SCOPE = ['openid', 'profile', 'email', 'User.Read']

    @property
    def tenant_id(self):
        return 'organizations'

    def jwks_url(self):
        return 'https://login.microsoftonline.com/common/discovery/keys'

    def auth_complete_params(self, state=None):
        ret = super().auth_complete_params(state)
        # Request access to the graph API
        ret['resource'] = 'https://graph.microsoft.com/'
        return ret

    def get_user_id(self, details, response):
        """Use oid claim as unique id."""
        oid = response['oid']
        # Replace the pairwise 'sub' field with the oid to better play along
        # with helusers.
        response['sub'] = oid
        return oid

    def get_user_details(self, response):
        details = super().get_user_details(response)
        # check `verified_primary_email` and enumerate through
        # `verified_secondary_email` to find possible matches
        # for `Person.email`
        # if self.client and self.client.use_id_token_email_field:
        #     details['email'] = response.get('email') or details.get('email')
        details['uuid'] = response.get('oid')
        return details

    def auth_extra_arguments(self):
        extra_arguments = super().auth_extra_arguments()
        request_data = self.strategy.request_data()
        email = request_data.get('email')
        if email:
            extra_arguments['login_hint'] = email
        return extra_arguments


class ADFSOpenIDConnectAuth(OpenIdConnectAuth):
    """ Integrate with an on-premises Microsoft ADFS implementation """
    name = 'adfs-openidconnect'
    # When more than one customer needs this backend,
    # we need to override the oidc_endpoint method somehow
    # and also get_key_and_secret (to support multiple confs per backend)
    OIDC_ENDPOINT = settings.SOCIAL_AUTH_ADFS_OPENIDCONNECT_API_URL

    def user_data(self, access_token, *args, **kwargs):
        # This method has been overridden because it is difficult to get the userinfo endpoint for ADFS working, and additionally the
        # endpoint isn't even needed. We already get all the relevant data in the id token.
        return {
            'username': self.id_token['unique_name'],
            'email': self.id_token['upn']
        }

    def get_user_id(self, details, response):
        return self.id_token['sub']
