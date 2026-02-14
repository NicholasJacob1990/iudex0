"""
Microsoft Graph API client with automatic retry, throttling handling, and pagination.
"""

import asyncio
import logging
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class GraphClient:
    """Client for Microsoft Graph API with retry and rate limiting."""

    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
    )
    async def get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET request with automatic retry on throttling."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = await self.client.get(url, params=params)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            logger.warning(f"Graph API throttled. Retry after {retry_after}s. Path: {path}")
            await asyncio.sleep(retry_after)
            raise httpx.HTTPStatusError(
                "Throttled", request=response.request, response=response
            )

        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
    )
    async def get_bytes(self, path: str, params: Optional[dict] = None) -> bytes:
        """GET request returning raw bytes (useful for attachment $value downloads)."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = await self.client.get(url, params=params)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            logger.warning(f"Graph API throttled. Retry after {retry_after}s. Path: {path}")
            await asyncio.sleep(retry_after)
            raise httpx.HTTPStatusError("Throttled", request=response.request, response=response)

        response.raise_for_status()
        return response.content

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
    )
    async def post(self, path: str, json_data: Optional[dict] = None) -> dict:
        """POST request with automatic retry on throttling."""
        url = f"{self.base_url}{path}"
        response = await self.client.post(url, json=json_data)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            logger.warning(f"Graph API throttled. Retry after {retry_after}s. Path: {path}")
            await asyncio.sleep(retry_after)
            raise httpx.HTTPStatusError(
                "Throttled", request=response.request, response=response
            )

        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(3),
    )
    async def patch(self, path: str, json_data: Optional[dict] = None) -> dict:
        """PATCH request with retry."""
        url = f"{self.base_url}{path}"
        response = await self.client.patch(url, json=json_data)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            await asyncio.sleep(retry_after)
            raise httpx.HTTPStatusError("Throttled", request=response.request, response=response)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(3),
    )
    async def delete(self, path: str) -> None:
        """DELETE request with retry."""
        url = f"{self.base_url}{path}"
        response = await self.client.delete(url)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            await asyncio.sleep(retry_after)
            raise httpx.HTTPStatusError("Throttled", request=response.request, response=response)
        response.raise_for_status()

    async def get_paginated(self, path: str, max_pages: int = 10) -> list:
        """Paginated GET with @odata.nextLink support."""
        results = []
        url = f"{self.base_url}{path}"
        for _ in range(max_pages):
            data = await self.get(url)
            results.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            url = next_link
        return results
