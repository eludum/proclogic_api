from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from datetime import datetime

from config.config import get_settings

settings = get_settings()

def get_token():

    if settings.pubproc_token_exp > datetime.now().timestamp():
        return settings.pubproc_token

    client_id = settings.pubproc_client_id
    client_secret = settings.pubproc_client_secret

    url = "https://public.pr.fedservices.be/api/oauth2/token"

    client = BackendApplicationClient(client_id=client_id)
    oauth = OAuth2Session(client=client)

    token = oauth.fetch_token(
        token_url=url,
        client_id=client_id,
        client_secret=client_secret,
        include_client_id=True,
    )

    settings.pubproc_token = token["access_token"]
    settings.pubproc_token_exp = token["expires_at"]
    
    return settings.pubproc_token
