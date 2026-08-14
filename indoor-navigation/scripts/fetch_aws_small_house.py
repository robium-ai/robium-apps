#!/usr/bin/env python3
"""Fetch a pinned AWS RoboMaker Small House asset into a Docker image."""

import argparse
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import urllib.request


REPOSITORY = 'aws-robotics/aws-robomaker-small-house-world'
DEFAULT_COMMIT = 'ff9631ca6d1db9c1ba656498151464b5ab74aafe'


def safe_members(archive, prefix):
    expected = PurePosixPath(prefix)
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or '..' in path.parts
            or not path.parts
            or path.parts[0] != str(expected)
            or member.issym()
            or member.islnk()
        ):
            raise ValueError(f'unsafe archive path: {member.name}')
        yield member


def fetch(commit, archive_url, destination):
    destination = Path(destination)
    prefix = f'aws-robomaker-small-house-world-{commit}'
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix='aws-small-house-', dir=destination.parent) as temporary_directory:
        temporary = Path(temporary_directory)
        archive_path = temporary / 'source.tar.gz'
        urllib.request.urlretrieve(archive_url, archive_path)
        with tarfile.open(archive_path, 'r:gz') as archive:
            archive.extractall(temporary, members=safe_members(archive, prefix))

        extracted = temporary / prefix
        required = (
            extracted / 'LICENSE',
            extracted / 'models',
            extracted / 'worlds' / 'small_house.world',
        )
        missing = [str(path.relative_to(extracted)) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f'AWS Small House archive is missing: {", ".join(missing)}')

        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(extracted), destination)

    (destination / 'SOURCE').write_text(
        f'https://github.com/{REPOSITORY}\ncommit {commit}\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', default=DEFAULT_COMMIT)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--archive-url')
    args = parser.parse_args()
    archive_url = args.archive_url or (
        f'https://github.com/{REPOSITORY}/archive/{args.commit}.tar.gz')
    fetch(args.commit, archive_url, args.destination)


if __name__ == '__main__':
    main()
