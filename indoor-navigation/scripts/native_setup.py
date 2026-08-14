#!/usr/bin/env python3
"""Install the app-local native macOS environment and Lichtblick assets."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

try:
    from scripts.native_paths import (
        NativeError,
        NativePaths,
        native_environment,
        require_apple_silicon,
    )
except ModuleNotFoundError:  # direct invocation: python3 scripts/native_setup.py
    from native_paths import (  # type: ignore[no-redef]
        NativeError,
        NativePaths,
        native_environment,
        require_apple_silicon,
    )


PIXI_VERSION = '0.69.0'
PIXI_URL = (
    f'https://github.com/prefix-dev/pixi/releases/download/v{PIXI_VERSION}/'
    'pixi-aarch64-apple-darwin.tar.gz')
PIXI_SHA256 = '640de30196141d6b67c745675cec6d6b784fb42df34b02ee25fde2bb2b542aac'
LICHTBLICK_REPOSITORY = 'lichtblick-suite/lichtblick'
LICHTBLICK_DIGEST = (
    'sha256:e29673ab12265fe84a62fed0835606d8789168fe9b3395a2997d97f002ed1e9d')
LAYOUT_PLACEHOLDER = '/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/'
MANIFEST_ACCEPT = ', '.join((
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.docker.distribution.manifest.v2+json',
))
PUBLISH_CLEANUP_PATTERN = re.compile(
    r'\(\)=>\{(\w+)\.unadvertise\?\.\((\w+)\.goal\),'
    r'\1\.unadvertise\?\.\(\2\.point\),'
    r'\1\.unadvertise\?\.\(\2\.pose\)\}')


def verify_digest(data: bytes, expected: str) -> None:
    algorithm, separator, wanted = expected.partition(':')
    if separator != ':' or algorithm != 'sha256':
        raise NativeError(f'unsupported artifact digest: {expected}')
    actual = hashlib.sha256(data).hexdigest()
    if actual != wanted:
        raise NativeError(
            f'artifact digest mismatch: expected {wanted}, got {actual}')


def _safe_member_path(destination: Path, name: str) -> tuple[Path, PurePosixPath]:
    member = PurePosixPath(name)
    if member.is_absolute() or '..' in member.parts:
        raise NativeError(f'unsafe OCI layer path: {name}')
    clean = PurePosixPath(*(
        part for part in member.parts if part not in ('', '.')
    ))
    target = destination.joinpath(*clean.parts)
    root = destination.resolve()
    parent = target.parent.resolve(strict=False)
    if parent != root and not parent.is_relative_to(root):
        raise NativeError(f'OCI layer path escapes destination: {name}')
    return target, clean


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def safe_extract_layer(stream, destination: Path, include_prefix: str | None = None) -> None:
    """Apply one compressed OCI tar layer without permitting path escapes."""
    destination.mkdir(parents=True, exist_ok=True)
    prefix = PurePosixPath(include_prefix) if include_prefix else None
    try:
        archive = tarfile.open(fileobj=stream, mode='r|*')
        for member in archive:
            _, clean = _safe_member_path(destination, member.name)
            if not clean.parts:
                continue
            if prefix and clean != prefix and prefix not in clean.parents:
                continue
            target, _ = _safe_member_path(destination, member.name)
            basename = target.name
            if basename == '.wh..wh..opq':
                target.parent.mkdir(parents=True, exist_ok=True)
                for child in target.parent.iterdir():
                    _remove_path(child)
                continue
            if basename.startswith('.wh.'):
                _remove_path(target.with_name(basename[4:]))
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            _remove_path(target)
            if member.isfile():
                source = archive.extractfile(member)
                if source is None:
                    raise NativeError(f'cannot read OCI layer file: {member.name}')
                with target.open('wb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
            elif member.issym():
                normalized = posixpath.normpath(
                    str(clean.parent / member.linkname))
                link_target = PurePosixPath(normalized)
                if link_target.is_absolute() or '..' in link_target.parts:
                    raise NativeError(
                        f'OCI symlink escapes destination: {member.name}')
                target.symlink_to(member.linkname)
            elif member.islnk():
                source, _ = _safe_member_path(destination, member.linkname)
                if not source.exists() or source.is_dir():
                    raise NativeError(f'unsafe OCI hardlink: {member.name}')
                os.link(source, target)
            else:
                raise NativeError(f'unsupported OCI layer entry: {member.name}')
    except (tarfile.TarError, OSError) as error:
        if isinstance(error, NativeError):
            raise
        raise NativeError(f'failed to extract OCI layer: {error}') from error


def inject_layout(viewer: Path, layout: Path) -> None:
    index = viewer / 'index.html'
    try:
        html = index.read_text()
        layout_text = layout.read_text()
    except OSError as error:
        raise NativeError(f'cannot read Lichtblick viewer/layout: {error}') from error
    if html.count(LAYOUT_PLACEHOLDER) != 1:
        raise NativeError('Lichtblick layout placeholder must occur exactly once')
    temporary = index.with_suffix('.tmp')
    temporary.write_text(html.replace(LAYOUT_PLACEHOLDER, layout_text))
    os.replace(temporary, index)


def neutralize_publish_cleanup(viewer: Path) -> Path:
    """Keep Lichtblick's 3D publish topics advertised for the WS session."""
    matches: list[tuple[Path, str]] = []
    try:
        bundles = viewer.glob('*.js')
        for bundle in bundles:
            text = bundle.read_text()
            if PUBLISH_CLEANUP_PATTERN.search(text):
                matches.append((bundle, text))
    except OSError as error:
        raise NativeError(f'cannot read Lichtblick JavaScript bundle: {error}') from error
    if len(matches) != 1:
        raise NativeError(
            'Lichtblick publish-cleanup pattern must occur in exactly one bundle; '
            f'found {len(matches)}')
    bundle, text = matches[0]
    rewritten, count = PUBLISH_CLEANUP_PATTERN.subn('()=>{}', text)
    if count != 1:
        raise NativeError(
            'Lichtblick publish-cleanup pattern must occur exactly once in '
            f'{bundle.name}; found {count}')
    temporary = bundle.with_suffix('.tmp')
    temporary.write_text(rewritten)
    os.replace(temporary, bundle)
    return bundle


def optimize_robot_camera(model_sdf: Path) -> None:
    """Reduce the upstream Waffle Pi pinhole camera from 30 Hz to 10 Hz."""
    try:
        tree = ET.parse(model_sdf)
    except (OSError, ET.ParseError) as error:
        raise NativeError(f'cannot read TurtleBot camera model: {error}') from error
    cameras = [sensor for sensor in tree.getroot().findall('.//sensor')
               if sensor.get('name') == 'camera' and sensor.get('type') == 'camera']
    if len(cameras) != 1:
        raise NativeError(
            'TurtleBot pinhole camera must occur exactly once; '
            f'found {len(cameras)}')
    update_rate = cameras[0].find('update_rate')
    if update_rate is None or update_rate.text not in ('10', '30'):
        value = None if update_rate is None else update_rate.text
        raise NativeError(
            f'TurtleBot camera update rate changed; expected 30 or 10, got {value}')
    if update_rate.text == '10':
        return
    update_rate.text = '10'
    temporary = model_sdf.with_suffix('.tmp')
    tree.write(temporary, encoding='unicode')
    os.replace(temporary, model_sdf)


def _download(url: str, headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read(), response.headers
    except OSError as error:
        raise NativeError(f'download failed for {url}: {error}') from error


def install_pixi(paths: NativePaths) -> None:
    if paths.pixi.is_file():
        result = subprocess.run(
            [str(paths.pixi), '--version'], capture_output=True, text=True,
            check=False)
        if result.returncode == 0 and result.stdout.strip() == f'pixi {PIXI_VERSION}':
            return
    payload, _ = _download(PIXI_URL)
    verify_digest(payload, f'sha256:{PIXI_SHA256}')
    paths.pixi.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=gzip.GzipFile(fileobj=__import__('io').BytesIO(payload)),
                      mode='r:') as archive:
        members = [member for member in archive.getmembers()
                   if PurePosixPath(member.name).name == 'pixi' and member.isfile()]
        if len(members) != 1:
            raise NativeError('Pixi archive does not contain exactly one executable')
        source = archive.extractfile(members[0])
        temporary = paths.pixi.with_suffix('.tmp')
        with temporary.open('wb') as output:
            shutil.copyfileobj(source, output)
    temporary.chmod(0o755)
    os.replace(temporary, paths.pixi)


def install_environment(paths: NativePaths) -> None:
    paths.auth.parent.mkdir(parents=True, exist_ok=True)
    if not paths.auth.exists():
        paths.auth.write_text('{}\n')
    command = [
        str(paths.pixi), 'install', '--locked',
        '--manifest-path', str(paths.experiment / 'pixi.toml'),
        '--auth-file', str(paths.auth),
    ]
    subprocess.run(command, env=native_environment(paths), check=True)
    optimize_robot_camera(
        paths.experiment / '.pixi' / 'envs' / 'default' / 'share' /
        'turtlebot3_gazebo' / 'models' / 'turtlebot3_waffle_pi' / 'model.sdf')


def _registry_token(repository: str) -> str:
    query = urllib.parse.urlencode({
        'service': 'ghcr.io',
        'scope': f'repository:{repository}:pull',
    })
    payload, _ = _download(f'https://ghcr.io/token?{query}')
    try:
        return json.loads(payload)['token']
    except (json.JSONDecodeError, KeyError) as error:
        raise NativeError('GHCR did not return an anonymous pull token') from error


def _fetch_manifest(repository: str, digest: str, token: str) -> dict:
    quoted = urllib.parse.quote(digest, safe=':')
    payload, headers = _download(
        f'https://ghcr.io/v2/{repository}/manifests/{quoted}',
        {'Authorization': f'Bearer {token}', 'Accept': MANIFEST_ACCEPT},
    )
    verify_digest(payload, digest)
    header_digest = headers.get('Docker-Content-Digest')
    if header_digest and header_digest != digest:
        raise NativeError(
            f'manifest header digest mismatch: expected {digest}, got {header_digest}')
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise NativeError('GHCR returned an invalid manifest') from error


def fetch_oci_image(repository: str, digest: str, destination: Path) -> None:
    token = _registry_token(repository)
    manifest = _fetch_manifest(repository, digest, token)
    if 'manifests' in manifest:
        candidates = [item for item in manifest['manifests']
                      if item.get('platform') == {
                          'architecture': 'amd64', 'os': 'linux'}]
        if len(candidates) != 1:
            raise NativeError('Lichtblick image has no unique linux/amd64 manifest')
        manifest = _fetch_manifest(repository, candidates[0]['digest'], token)

    for descriptor in manifest.get('layers', []):
        layer_digest = descriptor['digest']
        quoted = urllib.parse.quote(layer_digest, safe=':')
        payload, _ = _download(
            f'https://ghcr.io/v2/{repository}/blobs/{quoted}',
            {'Authorization': f'Bearer {token}'},
        )
        verify_digest(payload, layer_digest)
        safe_extract_layer(
            __import__('io').BytesIO(payload), destination, include_prefix='src')


def install_viewer(paths: NativePaths) -> None:
    paths.tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=paths.tmp) as temporary_name:
        root = Path(temporary_name) / 'image'
        fetch_oci_image(LICHTBLICK_REPOSITORY, LICHTBLICK_DIGEST, root)
        source = root / 'src'
        if not (source / 'index.html').is_file():
            raise NativeError('pinned Lichtblick image does not contain /src/index.html')
        staging = paths.runtime / 'viewer.new'
        _remove_path(staging)
        shutil.copytree(source, staging, symlinks=True)
        inject_layout(staging, paths.app_root / 'lichtblick' / 'nav-layout.json')
        neutralize_publish_cleanup(staging)
        _remove_path(paths.viewer)
        os.replace(staging, paths.viewer)


def main() -> int:
    if sys.argv[1:] == ['--version']:
        print(f'Pixi {PIXI_VERSION}; Lichtblick {LICHTBLICK_DIGEST}')
        return 0
    app_root = Path(__file__).resolve().parents[1]
    paths = NativePaths.from_app_root(app_root)
    try:
        require_apple_silicon()
        paths.ensure_runtime_directories()
        install_pixi(paths)
        install_environment(paths)
        install_viewer(paths)
    except (NativeError, subprocess.CalledProcessError) as error:
        print(f'native setup failed: {error}', file=sys.stderr)
        return 1
    print('native setup complete')
    subprocess.run(['du', '-sh', str(paths.experiment), str(paths.cache)],
                   check=False)
    print('next: make demo-native')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
