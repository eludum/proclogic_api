from datetime import datetime

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from app.config.settings import Settings

settings = Settings()


def get_token():

    if settings.pubproc_token and settings.pubproc_token_exp is not None:
        if settings.pubproc_token_exp > datetime.now().timestamp():
            return settings.pubproc_token

    client_id = settings.pubproc_client_id
    client_secret = settings.pubproc_client_secret

    url = settings.pubproc_token_url

    print(client_id, client_secret)
    print(url)

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
