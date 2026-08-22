import io
import os
import tarfile
import tempfile
import unittest
from email.message import Message
from unittest import mock
from urllib import error

import install
from action import http


def make_archive(member_name, contents=b'contents', mode=0o644):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(contents)
        member.mode = mode
        archive.addfile(member, io.BytesIO(contents))
    buffer.seek(0)
    return tarfile.open(fileobj=buffer, mode='r')


class LegacyArchive:
    """Expose the pre-filter TarFile.extract signature."""

    def __init__(self, archive):
        self.archive = archive

    def getmembers(self):
        return self.archive.getmembers()

    def extract(self, member, path):
        return self.archive.extract(member, path)


class ExtractArchiveTests(unittest.TestCase):
    def test_extracts_member_after_stripping_root_directory(self):
        with tempfile.TemporaryDirectory() as destination:
            with make_archive('wasi-sdk/bin/clang') as archive:
                install.extract_archive(archive, destination)

            with open(os.path.join(destination, 'bin', 'clang'), 'rb') as extracted:
                self.assertEqual(extracted.read(), b'contents')

    def test_rejects_member_outside_destination(self):
        with tempfile.TemporaryDirectory() as destination:
            with make_archive('wasi-sdk/../../escape') as archive:
                with self.assertRaises(tarfile.OutsideDestinationError):
                    install.extract_archive(archive, destination)

    def test_legacy_extract_api_extracts_safe_member(self):
        with tempfile.TemporaryDirectory() as destination:
            with make_archive('wasi-sdk/bin/clang', mode=0o6777) as archive:
                install.extract_archive(LegacyArchive(archive), destination)

            extracted = os.path.join(destination, 'bin', 'clang')
            self.assertTrue(os.path.isfile(extracted))
            self.assertEqual(os.stat(extracted).st_mode & 0o7777, 0o755)

    def test_legacy_extract_api_rejects_member_outside_destination(self):
        with tempfile.TemporaryDirectory() as destination:
            with make_archive('wasi-sdk/../../escape') as archive:
                with self.assertRaisesRegex(ValueError, 'outside'):
                    install.extract_archive(LegacyArchive(archive), destination)


class DownloadWithRetriesTests(unittest.TestCase):
    def setUp(self):
        jitter = mock.patch('action.http.random.uniform', return_value=0)
        self.random_uniform = jitter.start()
        self.addCleanup(jitter.stop)

    @staticmethod
    def http_error(status, headers=None):
        return error.HTTPError(
            'https://example.com/sdk.tar.gz', status, 'Error', headers or {}, None)

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_retries_network_errors_with_exponential_backoff(self, retrieve, sleep):
        retrieve.side_effect = [
            error.URLError(ConnectionResetError('connection reset')),
            error.URLError(TimeoutError('timed out')),
            None,
        ]

        http.download_with_retries('https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertEqual(retrieve.call_count, 3)
        sleep.assert_has_calls([mock.call(1), mock.call(2)])

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_retries_transient_http_errors(self, retrieve, sleep):
        unavailable = self.http_error(503)
        self.addCleanup(unavailable.close)
        retrieve.side_effect = [unavailable, None]

        http.download_with_retries('https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertEqual(retrieve.call_count, 2)
        sleep.assert_called_once_with(1)

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_does_not_retry_permanent_http_errors(self, retrieve, sleep):
        not_found = self.http_error(404)
        self.addCleanup(not_found.close)
        retrieve.side_effect = not_found

        with self.assertRaises(error.HTTPError):
            http.download_with_retries(
                'https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        retrieve.assert_called_once()
        sleep.assert_not_called()

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_raises_after_all_attempts(self, retrieve, sleep):
        retrieve.side_effect = error.URLError('network unavailable')

        with self.assertRaises(error.URLError):
            http.download_with_retries(
                'https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertEqual(retrieve.call_count, http.DOWNLOAD_ATTEMPTS)
        sleep.assert_has_calls([mock.call(1), mock.call(2), mock.call(4)])

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_adds_bounded_jitter_to_backoff(self, retrieve, sleep):
        self.random_uniform.return_value = 0.75
        retrieve.side_effect = [error.URLError('network unavailable'), None]

        http.download_with_retries('https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.random_uniform.assert_called_once_with(0, http.DOWNLOAD_JITTER_SECONDS)
        sleep.assert_called_once_with(1.75)

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_respects_retry_after(self, retrieve, sleep):
        headers = Message()
        headers['Retry-After'] = '17'
        rate_limited = self.http_error(429, headers)
        self.addCleanup(rate_limited.close)
        retrieve.side_effect = [rate_limited, None]

        http.download_with_retries('https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        sleep.assert_called_once_with(17)

    @mock.patch('action.http.time.time', return_value=1_000)
    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_respects_github_rate_limit_reset(self, retrieve, sleep, _time):
        headers = Message()
        headers['X-RateLimit-Remaining'] = '0'
        headers['X-RateLimit-Reset'] = '1042'
        rate_limited = self.http_error(403, headers)
        self.addCleanup(rate_limited.close)
        retrieve.side_effect = [rate_limited, None]

        http.download_with_retries('https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        sleep.assert_called_once_with(42)

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_does_not_retry_unrelated_forbidden_response(self, retrieve, sleep):
        forbidden = self.http_error(403)
        self.addCleanup(forbidden.close)
        retrieve.side_effect = forbidden

        with self.assertRaises(error.HTTPError):
            http.download_with_retries(
                'https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        retrieve.assert_called_once()
        sleep.assert_not_called()

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_does_not_retry_rate_limit_without_delay(self, retrieve, sleep):
        rate_limited = self.http_error(429)
        self.addCleanup(rate_limited.close)
        retrieve.side_effect = rate_limited

        with self.assertLogs(level='ERROR') as logs:
            with self.assertRaises(error.HTTPError):
                http.download_with_retries(
                    'https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertIn('did not provide a usable retry delay', logs.output[0])
        retrieve.assert_called_once()
        sleep.assert_not_called()

    @mock.patch('action.http.time.sleep')
    @mock.patch('action.http.request.urlretrieve')
    def test_does_not_wait_at_rate_limit_threshold(self, retrieve, sleep):
        headers = Message()
        headers['Retry-After'] = str(http.MAX_RATE_LIMIT_WAIT_SECONDS)
        rate_limited = self.http_error(429, headers)
        self.addCleanup(rate_limited.close)
        retrieve.side_effect = rate_limited

        with self.assertLogs(level='ERROR') as logs:
            with self.assertRaises(error.HTTPError):
                http.download_with_retries(
                    'https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertIn('is not less than', logs.output[0])
        retrieve.assert_called_once()
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
