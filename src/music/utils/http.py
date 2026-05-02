"""HTTP helpers backed by curl_cffi."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlencode

from curl_cffi import CurlOpt
from curl_cffi.requests import AsyncSession, Response

type BrowserType = Literal["chrome146"]
type HttpMethod = Literal[
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "OPTIONS",
    "HEAD",
    "TRACE",
    "PATCH",
    "QUERY",
]

DEFAULT_IMPERSONATE: BrowserType = "chrome146"


class ClientSession:
    """Thin async session wrapper with optional request logging."""

    def __init__(
        self,
        *,
        console: Any | None = None,
        curl_options: dict[CurlOpt, Any] | None = None,
        debug_http: bool = False,
    ) -> None:
        """Initialize."""
        self.console = console
        self.debug_http = debug_http
        self._session: AsyncSession[Response] = AsyncSession(
            default_headers=False,
            curl_options=curl_options,
            impersonate=DEFAULT_IMPERSONATE,
            trust_env=True,
        )

    async def __aenter__(self) -> "ClientSession":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Exit the async context manager."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying session."""
        await self._session.close()

    async def get(self, url: str, **kwargs: Any) -> Response:
        """Send a GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Response:
        """Send a POST request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Response:
        """Send a PUT request."""
        return await self.request("PUT", url, **kwargs)

    async def put_file(
        self,
        url: str,
        fil: Path,
        *,
        progress: Callable[[int], Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Send a PUT request streaming the request body from a file."""
        with fil.open("rb") as fobj:
            reader = _ProgressReader(fobj, progress)
            async with ClientSession(
                console=self.console,
                curl_options={
                    CurlOpt.UPLOAD: 1,
                    CurlOpt.READDATA: reader,
                    CurlOpt.INFILESIZE_LARGE: fil.stat().st_size,
                },
                debug_http=self.debug_http,
            ) as upload_client:
                return await upload_client.put(url, **kwargs)

    async def request(self, method: HttpMethod, url: str, **kwargs: Any) -> Response:
        """Send an HTTP request."""
        headers = kwargs.get("headers")
        params = kwargs.get("params")
        final_url = _url_with_params(url, params)

        if self.debug_http:
            self._print_request(method, final_url, headers)

        response = await self._session.request(method, url, **kwargs)

        if self.debug_http:
            self._print_response(method, final_url, response.status_code)

        return response

    def _print_request(
        self, method: HttpMethod, final_url: str, headers: dict[str, str] | None
    ) -> None:
        """Print an outgoing request in a curl-debug-friendly format."""
        if not self.console:
            return

        self.console.print(f"[dim]HTTP {method} {final_url}[/dim]", markup=True)
        host = final_url.split("/")[2]
        self.console.print(f"[dim]Host: {host}[/dim]", markup=True)

        for key, value in (headers or {}).items():
            self.console.print(
                f"[dim]{key}: {_redact_http_header_value(key, value)}[/dim]",
                markup=True,
            )

    def _print_response(
        self, method: HttpMethod, final_url: str, status_code: int
    ) -> None:
        """Print a response status line."""
        if not self.console:
            return

        self.console.print(
            f"[dim]HTTP {status_code} {method} {final_url}[/dim]",
            markup=True,
        )


def _url_with_params(url: str, params: dict[str, Any] | None) -> str:
    """Build a human-readable URL including query params."""
    if not params:
        return url

    query = urlencode(params)
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{query}"


def raise_for_status(resp: Response) -> None:
    """Raise the underlying curl_cffi HTTP status exception."""
    raise_for_status_ = cast(Callable[[], None], resp.raise_for_status)
    raise_for_status_()


class _ProgressReader:
    """File-like reader that reports bytes as curl consumes them."""

    def __init__(self, fobj: Any, progress: Callable[[int], Any] | None = None) -> None:
        self.fobj = fobj
        self.progress = progress

    def read(self, size: int) -> bytes:
        """Read bytes and report the number consumed."""
        chunk = self.fobj.read(size)
        if chunk and self.progress:
            self.progress(len(chunk))
        return cast(bytes, chunk)


def _redact_http_header_value(key: str, value: str) -> str:
    """Redact secrets in debug header output."""
    lower_key = key.lower()
    if lower_key == "authorization":
        return "OAuth <redacted>"
    if lower_key == "x-datadome-clientid":
        return "<redacted>"
    return value
