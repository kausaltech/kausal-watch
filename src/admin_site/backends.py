from __future__ import annotations

from typing import override

from django.conf import settings

from jwt import DecodeError, ExpiredSignatureError, PyJWK, decode as jwt_decode
from social_core.backends.open_id_connect import OpenIdConnectAuth
from social_core.exceptions import AuthTokenError

from kausal_common.auth.backends import AzureADAuth


class SingleTenantSpecificEntraAuth(AzureADAuth):
    #  If more tenants are needed, add another subclass like this with something appended to the name
    #  and the configuration variable names
    name = settings.SINGLE_TENANT_SPECIFIC_ENTRA_BACKEND_NAME

    @property
    @override
    def tenant_id(self):
        return settings.SINGLE_TENANT_SPECIFIC_ENTRA_TENANT_ID

    @override
    def get_key_and_secret(self):
        return (settings.SINGLE_TENANT_SPECIFIC_ENTRA_KEY, settings.SINGLE_TENANT_SPECIFIC_ENTRA_SECRET)

    @override
    def user_data(self, access_token, *args, **kwargs):
        response = kwargs.get('response')
        assert response is not None
        id_token = response.get('id_token')

        try:
            from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

            key = self.get_id_token_key(id_token)
            public_key = PyJWK(key).key
            assert isinstance(public_key, (rsa.RSAPublicKey, ec.EllipticCurvePublicKey, ed25519.Ed25519PublicKey))
            return jwt_decode(
                id_token,
                key=public_key,
                algorithms=['RS256'],
                audience=settings.SINGLE_TENANT_SPECIFIC_ENTRA_KEY,
            )
        except (DecodeError, ExpiredSignatureError) as error:
            raise AuthTokenError(self) from error


class ADFSOpenIDConnectAuth(OpenIdConnectAuth):
    """Integrate with an on-premises Microsoft ADFS implementation."""

    name = 'adfs-openidconnect'
    # When more than one customer needs this backend,
    # we need to override the oidc_endpoint method somehow
    # and also get_key_and_secret (to support multiple confs per backend)
    OIDC_ENDPOINT = settings.SOCIAL_AUTH_ADFS_OPENIDCONNECT_API_URL

    def user_data(self, access_token, *args, **kwargs):
        # This method has been overridden because it is difficult to get the userinfo endpoint for ADFS working, and
        # additionally the endpoint isn't even needed. We already get all the relevant data in the id token.
        assert self.id_token is not None
        return {
            'username': self.id_token['unique_name'],
            'email': self.id_token['upn'],
        }

    def get_user_id(self, details, response):
        assert self.id_token is not None
        return self.id_token['sub']
