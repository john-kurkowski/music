"""Authentication for the SoundCloud API."""

import urllib.parse
import webbrowser
import wsgiref.simple_server
from collections.abc import Iterable
from typing import Any
from wsgiref.types import StartResponse

import requests


def login(client_id: str, client_secret: str) -> str:
    """Log the user into SoundCloud."""
    port = 8080
    redirect_uri = f"http://localhost:{port}/"

    webbrowser.open(
        f"https://api.soundcloud.com/connect?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code"
    )

    code = ""
    exception: Exception | None = None

    def _application(
        environ: dict[str, Any], start_response: StartResponse
    ) -> Iterable[bytes]:
        """WSGI application for the local server."""
        try:
            query_string = environ["QUERY_STRING"]
            query_params = urllib.parse.parse_qs(query_string)
            nonlocal code
            code = query_params["code"][0]
            start_response("200 OK", [("Content-type", "text/plain")])
            return [b"Authorization successful. You can close this window."]
        except Exception as e:
            nonlocal exception
            exception = e
            raise

    server = wsgiref.simple_server.make_server("localhost", port, _application)
    server.handle_request()
    server.server_close()
    if exception:
        raise exception

    auth_resp = requests.post(
        "https://api.soundcloud.com/oauth2/token",
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=10,
    )
    auth_resp.raise_for_status()
    auth = auth_resp.json()
    return str(auth["access_token"])
