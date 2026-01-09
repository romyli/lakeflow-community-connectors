"""
Zoho CRM API Client.

Handles authentication, HTTP requests, and pagination for the Zoho CRM API.
This module separates API concerns from business logic.
"""

import re
import time
from datetime import datetime, timedelta
from typing import Iterator, Optional

import requests


class ZohoAPIClient:
    """
    HTTP client for Zoho CRM API with OAuth2 authentication.

    Handles:
    - OAuth2 token refresh
    - Rate limiting with exponential backoff
    - Paginated API responses
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        accounts_url: str = "https://accounts.zoho.com",
    ) -> None:
        """
        Initialize the API client.

        Args:
            client_id: OAuth Client ID from Zoho API Console
            client_secret: OAuth Client Secret from Zoho API Console
            refresh_token: Long-lived refresh token from OAuth flow
            accounts_url: Zoho accounts URL for OAuth (region-specific)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.accounts_url = accounts_url.rstrip("/")

        # Derive API URL from accounts URL
        # https://accounts.zoho.eu -> https://www.zohoapis.eu
        match = re.search(r"accounts\.zoho\.(.+)$", self.accounts_url)
        domain_suffix = match.group(1) if match else "com"
        self.api_url = f"https://www.zohoapis.{domain_suffix}"

        # Token management
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        # HTTP session for connection pooling
        self._session = requests.Session()

    def _get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        Access tokens expire after 1 hour (3600 seconds).
        """
        # Check if we have a valid token (with 5-minute buffer)
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=5):
                return self._access_token

        # Refresh the token
        token_url = f"{self.accounts_url}/oauth/v2/token"
        data = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }

        response = requests.post(token_url, data=data, timeout=30)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"Failed to refresh access token: {e}. Response: {response.text}")

        token_data = response.json()

        if "access_token" not in token_data:
            raise Exception(
                f"Token refresh response missing 'access_token'. "
                f"Response: {token_data}. "
                f"Please check your client_id, client_secret, and refresh_token are valid."
            )

        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

        return self._access_token

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        max_retries: int = 3,
    ) -> dict:
        """
        Make an authenticated API request to Zoho CRM.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (e.g., "/crm/v8/Leads")
            params: Query parameters
            data: Request body for POST/PUT
            max_retries: Maximum retry attempts for rate limiting

        Returns:
            Parsed JSON response as dictionary

        Raises:
            Exception: On API errors after retries exhausted
        """
        access_token = self._get_access_token()
        url = f"{self.api_url}{endpoint}"
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

        if data:
            headers["Content-Type"] = "application/json"

        for attempt in range(max_retries):
            try:
                response = self._make_http_request(method, url, headers, params, data)

                # Handle rate limiting
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        time.sleep(wait_time)
                        continue
                    raise Exception("Rate limit exceeded. Please wait and try again later.")

                response.raise_for_status()

                # Handle empty responses
                if not response.text or response.text.strip() == "":
                    return {}

                return response.json()

            except requests.exceptions.HTTPError as e:
                # Retry once with fresh token on 401
                if e.response.status_code == 401 and attempt == 0:
                    self._access_token = None
                    access_token = self._get_access_token()
                    headers["Authorization"] = f"Zoho-oauthtoken {access_token}"
                    continue
                raise

        raise Exception(f"Failed to make request after {max_retries} attempts")

    def _make_http_request(
        self,
        method: str,
        url: str,
        headers: dict,
        params: Optional[dict],
        data: Optional[dict],
    ) -> requests.Response:
        """
        Execute the actual HTTP request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Full URL to request
            headers: Request headers including Authorization
            params: Query parameters
            data: Request body for POST/PUT

        Returns:
            requests.Response object

        Raises:
            ValueError: For unsupported HTTP methods
        """
        method = method.upper()
        if method == "GET":
            return self._session.get(url, headers=headers, params=params)
        elif method == "POST":
            return self._session.post(url, headers=headers, json=data, params=params)
        elif method == "PUT":
            return self._session.put(url, headers=headers, json=data, params=params)
        elif method == "DELETE":
            return self._session.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    def paginate(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        data_key: str = "data",
        per_page: int = 200,
    ) -> Iterator[dict]:
        """
        Iterate through paginated API responses.

        Args:
            endpoint: API endpoint path
            params: Base query parameters (page/per_page will be added)
            data_key: Key in response containing the data array
            per_page: Number of records per page (max 200 for Zoho)

        Yields:
            Individual records from each page
        """
        params = dict(params) if params else {}
        page = 1

        while True:
            params["page"] = page
            params["per_page"] = per_page

            response = self.request("GET", endpoint, params=params)
            data = response.get(data_key, [])
            info = response.get("info", {})

            yield from data

            if not info.get("more_records", False) or not data:
                break

            page += 1

    def paginate_with_info(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        data_key: str = "data",
        per_page: int = 200,
    ) -> Iterator[tuple[list[dict], dict]]:
        """
        Iterate through paginated API responses, yielding page data with info.

        Useful when you need access to pagination metadata.

        Args:
            endpoint: API endpoint path
            params: Base query parameters
            data_key: Key in response containing the data array
            per_page: Number of records per page

        Yields:
            Tuples of (records_list, info_dict) for each page
        """
        params = dict(params) if params else {}
        page = 1

        while True:
            params["page"] = page
            params["per_page"] = per_page

            response = self.request("GET", endpoint, params=params)
            data = response.get(data_key, [])
            info = response.get("info", {})

            yield data, info

            if not info.get("more_records", False) or not data:
                break

            page += 1
