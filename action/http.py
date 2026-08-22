"""HTTP download and retry utilities."""

import datetime
import email.utils
import logging
import os
import random
import time
from urllib import error, request

DOWNLOAD_ATTEMPTS = 4
DOWNLOAD_BACKOFF_SECONDS = 1
DOWNLOAD_JITTER_SECONDS = 1
MAX_RATE_LIMIT_WAIT_SECONDS = 60
RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


def github_api_request(url: str):
    """Create an authenticated request for the GitHub API."""
    req = request.Request(url)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    if 'GITHUB_TOKEN' in os.environ:
        req.add_header('Authorization', f'Bearer {os.environ["GITHUB_TOKEN"]}')
    return req


def download_with_retries(url: str, destination: str):
    """Download a URL, retrying transient failures with exponential backoff."""
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        server_retry_delay = None
        try:
            request.urlretrieve(url, destination)
            return
        except error.HTTPError as exc:
            server_retry_delay = retry_delay_from_headers(exc.headers)
            has_github_rate_limit_headers = (
                exc.headers.get('Retry-After') is not None
                or exc.headers.get('X-RateLimit-Remaining') == '0')
            is_github_rate_limit = (
                exc.code == 429
                or exc.code == 403 and has_github_rate_limit_headers)
            if is_github_rate_limit:
                if server_retry_delay is None:
                    logging.error(
                        f'Rate limited with HTTP {exc.code}, but the server did not '
                        'provide a usable retry delay; not retrying')
                    raise
                if server_retry_delay >= MAX_RATE_LIMIT_WAIT_SECONDS:
                    logging.error(
                        f'Rate limited with HTTP {exc.code}; the server requested a '
                        f'{server_retry_delay}-second wait, which is not less than '
                        f'the {MAX_RATE_LIMIT_WAIT_SECONDS}-second limit; not retrying')
                    raise
                logging.warning(
                    f'Rate limited with HTTP {exc.code}; the server requested a '
                    f'{server_retry_delay}-second wait before retrying')
            if (exc.code not in RETRYABLE_HTTP_STATUS_CODES
                    and not is_github_rate_limit):
                raise
            download_error = exc
        except (error.URLError, ConnectionError, TimeoutError) as exc:
            download_error = exc

        if attempt == DOWNLOAD_ATTEMPTS:
            raise download_error

        base_delay = (server_retry_delay if server_retry_delay is not None
                      else DOWNLOAD_BACKOFF_SECONDS * 2 ** (attempt - 1))
        delay = base_delay + random.uniform(0, DOWNLOAD_JITTER_SECONDS)
        logging.warning(
            f'Download attempt {attempt}/{DOWNLOAD_ATTEMPTS} failed: '
            f'{download_error}. Retrying in {delay} seconds')
        time.sleep(delay)


def retry_delay_from_headers(headers):
    """Return a server-requested retry delay, including GitHub rate limits."""
    retry_after = headers.get('Retry-After')
    if retry_after is not None:
        try:
            return max(0, int(retry_after))
        except ValueError:
            try:
                retry_at = email.utils.parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=datetime.timezone.utc)
                return max(0, retry_at.timestamp() - time.time())
            except (TypeError, ValueError):
                pass

    if headers.get('X-RateLimit-Remaining') == '0':
        try:
            return max(0, int(headers['X-RateLimit-Reset']) - time.time())
        except (KeyError, TypeError, ValueError):
            pass

    return None
