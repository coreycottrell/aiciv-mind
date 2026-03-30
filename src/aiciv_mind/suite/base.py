"""Base HTTP client with retry and error handling."""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class ServiceError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {}


class BaseServiceClient:
    """Shared httpx.AsyncClient with retry and structured error handling."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def get(
        self,
        path: str,
        headers: dict | None = None,
        **kwargs,
    ) -> dict:
        """GET request. Raises ServiceError on non-2xx."""
        response = await self._client.get(path, headers=headers, **kwargs)
        self._raise_for_status(response)
        return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def post(
        self,
        path: str,
        json: dict | None = None,
        headers: dict | None = None,
        **kwargs,
    ) -> dict:
        """POST request. Raises ServiceError on non-2xx."""
        response = await self._client.post(path, json=json, headers=headers, **kwargs)
        self._raise_for_status(response)
        return response.json()

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise ServiceError if response is not 2xx."""
        if response.is_success:
            return
        try:
            detail = response.json()
        except Exception:
            detail = {"raw": response.text}
        message = detail.get("detail", response.text) if isinstance(detail, dict) else str(detail)
        raise ServiceError(
            f"HTTP {response.status_code}: {message}",
            status_code=response.status_code,
            detail=detail if isinstance(detail, dict) else {"raw": str(detail)},
        )

    async def close(self) -> None:
        await self._client.aclose()
