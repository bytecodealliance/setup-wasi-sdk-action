#!/usr/bin/env python

# Install a specific version of the WASI SDK. This is primarily intended for cross-platform use
# within GitHub Actions but can be used locally as well.
#
# Usage: install.py --version 25.0 --install-dir /path/to/install
#
# See `install.py --help` for more options.


import argparse
import doctest
import hashlib
import json
import logging
import os
import platform
import re
import sys
import tarfile
import tempfile
from urllib import parse, request


def github_api_request(url: str):
    """Create an authenticated request for the GitHub API."""
    req = request.Request(url)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    if 'GITHUB_TOKEN' in os.environ:
        req.add_header('Authorization', f'Bearer {os.environ["GITHUB_TOKEN"]}')
    return req


def retrieve_latest_tag():
    """
    Retrieve the tag of a WASI SDK artifact from the latest GitHub releases.

    >>> retrieve_latest_tag()[:9]
    'wasi-sdk-'
    """
    url = 'https://api.github.com/repos/WebAssembly/wasi-sdk/releases/latest'
    # Because macos runners share the same IP, unauthenticated requests are
    # immediately rate-limited by GitHub (https://github.com/actions/runner-images/issues/602).
    req = github_api_request(url)
    with request.urlopen(req) as response:
        data = json.loads(response.read().decode('utf-8'))
        return data['tag_name']


def find_asset_digest(release: dict, artifact_name: str):
    """
    Find and validate an artifact's SHA-256 digest in GitHub release metadata.

    >>> release = {'assets': [{'name': 'sdk.tar.gz', 'digest': 'sha256:' + 'a' * 64}]}
    >>> find_asset_digest(release, 'sdk.tar.gz')
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    >>> find_asset_digest({'assets': []}, 'missing.tar.gz')
    Traceback (most recent call last):
        ...
    ValueError: Release metadata does not contain asset 'missing.tar.gz'
    >>> find_asset_digest({'assets': [{'name': 'sdk.tar.gz', 'digest': None}]}, 'sdk.tar.gz')
    Traceback (most recent call last):
        ...
    ValueError: Release asset 'sdk.tar.gz' does not have a valid SHA-256 digest
    """
    asset = next(
        (asset for asset in release.get('assets', [])
         if asset.get('name') == artifact_name),
        None)
    if asset is None:
        raise ValueError(
            f'Release metadata does not contain asset {artifact_name!r}')

    digest = asset.get('digest')
    if (not isinstance(digest, str)
            or re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest) is None):
        raise ValueError(
            f'Release asset {artifact_name!r} does not have a valid SHA-256 digest')
    return digest.lower()


def retrieve_asset_digest(tag: str, artifact_name: str):
    """Retrieve an artifact's published digest from its GitHub release."""
    encoded_tag = parse.quote(tag, safe='')
    url = ('https://api.github.com/repos/WebAssembly/wasi-sdk/releases/tags/'
           f'{encoded_tag}')
    with request.urlopen(github_api_request(url)) as response:
        release = json.loads(response.read().decode('utf-8'))
    return find_asset_digest(release, artifact_name)


def verify_download(file_path: str, expected_digest: str, artifact_name: str):
    """
    Verify a downloaded file against its published SHA-256 digest.

    >>> validate_digest('a' * 64, 'sha256:' + 'a' * 64, 'sdk.tar.gz')
    >>> validate_digest('b' * 64, 'sha256:' + 'a' * 64, 'sdk.tar.gz')
    Traceback (most recent call last):
        ...
    ValueError: SHA-256 verification failed for 'sdk.tar.gz': expected aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, got bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    """
    digest = hashlib.sha256()
    with open(file_path, 'rb') as downloaded:
        for chunk in iter(lambda: downloaded.read(1024 * 1024), b''):
            digest.update(chunk)
    validate_digest(digest.hexdigest(), expected_digest, artifact_name)


def validate_digest(actual: str, expected_digest: str, artifact_name: str):
    """Compare a calculated SHA-256 value with a published digest."""
    expected = expected_digest.removeprefix('sha256:')
    if actual.lower() != expected.lower():
        raise ValueError(
            f'SHA-256 verification failed for {artifact_name!r}: '
            f'expected {expected}, got {actual}')


def calculate_version_and_tag(version: str):
    """
    Normalize the passed version string into a valid version number and release tag.

    >>> calculate_version_and_tag('25')
    ('25.0', 'wasi-sdk-25')
    >>> calculate_version_and_tag('25.0')
    ('25.0', 'wasi-sdk-25')
    >>> calculate_version_and_tag('25.1')
    ('25.1', 'wasi-sdk-25.1')
    >>> calculate_version_and_tag('30')
    ('30.0', 'wasi-sdk-30')
    >>> calculate_version_and_tag('30.10')
    ('30.10', 'wasi-sdk-30.10')
    >>> latest = calculate_version_and_tag('latest')
    >>> float(latest[0]) > 0
    True
    >>> latest[1].startswith('wasi-sdk-')
    True
    >>> float(latest[1].removeprefix('wasi-sdk-')) > 0
    True
    """
    if version == 'latest':
        tag = retrieve_latest_tag()
        version = tag.replace('wasi-sdk-', '')
    else:
        stripped = version.removesuffix('.0')
        tag = f'wasi-sdk-{stripped}'

    if '.' not in version:
        version = f'{version}.0'

    return version, tag


def calculate_artifact_url(version: str, tag: str, arch: str, os_name: str):
    """
    Generate the artifact URL based on the version, architecture, and operating system.

    >>> calculate_artifact_url('25.0', 'wasi-sdk-25', 'x86_64', 'Linux')
    'https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-25/wasi-sdk-25.0-x86_64-linux.tar.gz'
    >>> calculate_artifact_url('25.1', 'wasi-sdk-25.1', 'arm64', 'Darwin')
    'https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-25.1/wasi-sdk-25.1-arm64-macos.tar.gz'
    >>> calculate_artifact_url('30.0', 'wasi-sdk-30', 'aarch64', 'Linux')
    'https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-30/wasi-sdk-30.0-arm64-linux.tar.gz'
    """
    base = 'https://github.com/WebAssembly/wasi-sdk/releases/download'
    match os_name.lower():
        case 'darwin':
            os_name = 'macos'
        case rest:
            os_name = rest
    match arch.lower():
        case 'amd64':
            arch = 'x86_64'
        case 'aarch64':
            arch = 'arm64'
        case rest:
            arch = rest
    return f'{base}/{tag}/wasi-sdk-{version}-{arch}-{os_name}.tar.gz'


def install(url: str, install_dir: str, expected_digest: str):
    """
    Download the file from the given URL and extract it to a directory.
    """
    logging.info(f'Downloading {url}')
    file = tempfile.NamedTemporaryFile(delete=False)
    file.close()  # Close the handle so Windows can access the file
    try:
        request.urlretrieve(url, file.name)
        logging.info(f'Successfully downloaded {file.name}')

        artifact_name = url.rsplit('/', 1)[-1]
        verify_download(file.name, expected_digest, artifact_name)
        logging.info(f'Verified SHA-256 digest for {artifact_name}')

        os.makedirs(install_dir, exist_ok=True)
        with tarfile.open(file.name, 'r:gz') as tar:
            for member in tar.getmembers():
                # Strip off the first path component (i.e., `--strip-components=1`).
                parts = member.name.split('/')
                if len(parts) > 1:
                    member.name = '/'.join(parts[1:])
                    # Eventually we will want to pass `filter='tar'` here, but Windows runners have a
                    # pre-3.9.17 version of Python.
                    tar.extract(member, path=install_dir)
        logging.info(f'Extracted to {install_dir}')
    finally:
        os.unlink(file.name)
        logging.debug(f'Cleaned up temporary file {file.name}')

    sep = os.path.sep
    ext = '.exe' if sep == '\\' else ''
    clang_path = f'{install_dir}{sep}bin{sep}clang{ext}'
    assert os.path.isfile(clang_path), f'clang not found at {clang_path}'
    logging.info(f'Found Clang executable: {clang_path}')

    sysroot_path = f'{install_dir}{sep}share{sep}wasi-sysroot'
    assert os.path.isdir(sysroot_path), f'sysroot not found at {sysroot_path}'
    logging.info(f'Found WASI sysroot: {sysroot_path}')

    return clang_path, sysroot_path


def write_github_env(install_dir: str, version: str):
    """
    Write informational WASI SDK environment variables to GitHub Actions.
    """
    assert 'GITHUB_ENV' in os.environ, "GITHUB_ENV environment variable must be set"
    env_file = os.environ['GITHUB_ENV']
    logging.info(f'Writing to GitHub environment file {env_file}')
    with open(env_file, 'a') as f:
        f.write(f'WASI_SDK_PATH={install_dir}\n')
        f.write(f'WASI_SDK_VERSION={version}\n')


def write_github_path(install_dir: str, clang_path: str, sysroot_path: str):
    """
    Write the WASI SDK bin directory to GitHub PATH and set CC/CXX environment variables.
    """
    assert 'GITHUB_PATH' in os.environ, "GITHUB_PATH environment variable must be set"
    path_file = os.environ['GITHUB_PATH']
    logging.info(f'Writing to GitHub path file {path_file}')
    with open(path_file, 'a') as f:
        f.write(os.path.dirname(clang_path))

    env_file = os.environ['GITHUB_ENV']
    logging.info(f'Writing CC/CXX to GitHub environment file {env_file}')
    with open(env_file, 'a') as f:
        f.write(f'CC={clang_path} --sysroot={sysroot_path}\n')
        f.write(f'CXX={clang_path}++ --sysroot={sysroot_path}\n')


def write_github_output(install_dir: str, version: str, clang_path: str, sysroot_path: str):
    """
    Write the WASI SDK path and version to the GitHub Actions output file.
    """
    assert 'GITHUB_OUTPUT' in os.environ, "GITHUB_OUTPUT environment variable must be set"
    output_file = os.environ['GITHUB_OUTPUT']
    logging.info(f'Writing to GitHub output file {output_file}')
    with open(output_file, 'a') as f:
        f.write(f'wasi-sdk-path={install_dir}\n')
        f.write(f'wasi-sdk-version={version}\n')
        f.write(f'clang-path={clang_path}\n')
        f.write(f'sysroot-path={sysroot_path}\n')


def main(version: str, install_dir: str, add_to_path: bool):
    install_dir = os.path.abspath(install_dir)
    version, tag = calculate_version_and_tag(version)
    url = calculate_artifact_url(
        version, tag, platform.machine(), platform.system())

    artifact_name = url.rsplit('/', 1)[-1]
    expected_digest = retrieve_asset_digest(tag, artifact_name)
    clang_path, sysroot_path = install(url, install_dir, expected_digest)

    if 'GITHUB_ENV' in os.environ:
        write_github_env(install_dir, version)
    if add_to_path:
        write_github_path(install_dir, clang_path, sysroot_path)
    if 'GITHUB_OUTPUT' in os.environ:
        write_github_output(install_dir, version, clang_path, sysroot_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Install a version of WASI SDK.')
    parser.add_argument(
        '--version', help='The version to install (e.g., `25.0`).', default='latest')
    parser.add_argument(
        '--install-dir', help='The directory to install to; defaults to the current directory', default='.')
    parser.add_argument(
        '--add-to-path', help='Write the installed binary directory to GitHub\'s path file (e.g., \
            `$GITHUB_PATH`).', default=False, action='store_true')
    parser.add_argument(
        '-v', '--verbose', help='Increase the logging level.', action='count', default=0)
    parser.add_argument(
        '--test-only', help='Run the script\'s doctests and exit', action='store_true', default=False)
    args = parser.parse_args()

    # Setup logging.
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    logging.getLogger().name = os.path.basename(__file__)

    if args.test_only:
        failures, _ = doctest.testmod(verbose=args.verbose)
        if failures:
            sys.exit(1)
    else:
        main(args.version, args.install_dir, args.add_to_path)
