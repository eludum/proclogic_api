from datetime import datetime

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from app.config.settings import settings

# Treat a token as expired this many seconds before it actually is.
#
# Without the buffer the cache handed out a token that was still valid at the
# instant of the check and expired in flight: the scraper's first BOSA search
# then came back 401 "Ongeautoriseerd. Autorisatie is ongeldig of verlopen."
# and aborted the whole daily run. BOSA's tokens are short-lived, the clocks on
# either side are not synchronised, and a request costs a round trip -- a
# minute of slack is cheap and removes the race.
TOKEN_EXPIRY_LEEWAY_SECONDS = 60


def clear_token():
    """Drop the cached token so the next get_token() fetches a fresh one.

    Called when BOSA rejects a request we believed was authorised: the token
    was revoked, or expired despite the leeway. Re-fetching is the only way to
    recover -- otherwise the cache keeps replaying the dead token until its
    recorded expiry passes.
    """
    settings.pubproc_token = ""
    settings.pubproc_token_exp = ""


def get_token():

    if settings.pubproc_token and settings.pubproc_token_exp:
        # expires_at arrives from oauthlib as a float; the setting is declared
        # str, so coerce rather than trust whichever one last wrote it.
        expires_at = float(settings.pubproc_token_exp)
        if expires_at - TOKEN_EXPIRY_LEEWAY_SECONDS > datetime.now().timestamp():
            return settings.pubproc_token

    client_id = settings.pubproc_client_id
    client_secret = settings.pubproc_client_secret

    url = settings.pubproc_token_url

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
