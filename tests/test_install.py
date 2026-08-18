import io
import os
import tarfile
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
