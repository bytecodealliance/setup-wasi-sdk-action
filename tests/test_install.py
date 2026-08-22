import io
import os
import tarfile
import tempfile
import unittest
from unittest import mock
from urllib import error

import install


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
    @mock.patch('install.time.sleep')
    @mock.patch('install.request.urlretrieve')
    def test_retries_network_errors_with_exponential_backoff(self, retrieve, sleep):
        retrieve.side_effect = [
            error.URLError(ConnectionResetError('connection reset')),
            error.URLError(TimeoutError('timed out')),
            None,
        ]

        install.download_with_retries('https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertEqual(retrieve.call_count, 3)
        sleep.assert_has_calls([mock.call(1), mock.call(2)])

    @mock.patch('install.time.sleep')
    @mock.patch('install.request.urlretrieve')
    def test_retries_transient_http_errors(self, retrieve, sleep):
        unavailable = error.HTTPError(
            'https://example.com/sdk.tar.gz', 503, 'Unavailable', {}, None)
        self.addCleanup(unavailable.close)
        retrieve.side_effect = [unavailable, None]

        install.download_with_retries('https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertEqual(retrieve.call_count, 2)
        sleep.assert_called_once_with(1)

    @mock.patch('install.time.sleep')
    @mock.patch('install.request.urlretrieve')
    def test_does_not_retry_permanent_http_errors(self, retrieve, sleep):
        not_found = error.HTTPError(
            'https://example.com/sdk.tar.gz', 404, 'Not Found', {}, None)
        self.addCleanup(not_found.close)
        retrieve.side_effect = not_found

        with self.assertRaises(error.HTTPError):
            install.download_with_retries(
                'https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        retrieve.assert_called_once()
        sleep.assert_not_called()

    @mock.patch('install.time.sleep')
    @mock.patch('install.request.urlretrieve')
    def test_raises_after_all_attempts(self, retrieve, sleep):
        retrieve.side_effect = error.URLError('network unavailable')

        with self.assertRaises(error.URLError):
            install.download_with_retries(
                'https://example.com/sdk.tar.gz', '/tmp/sdk.tar.gz')

        self.assertEqual(retrieve.call_count, install.DOWNLOAD_ATTEMPTS)
        sleep.assert_has_calls([mock.call(1), mock.call(2), mock.call(4)])


if __name__ == '__main__':
    unittest.main()
