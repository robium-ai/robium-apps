import gzip
import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.native_paths import NativeError


def layer(entries):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == 'file':
                data = content.encode()
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            elif kind == 'directory':
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            elif kind == 'symlink':
                info.type = tarfile.SYMTYPE
                info.linkname = content
                archive.addfile(info)
    return io.BytesIO(gzip.compress(payload.getvalue()))


class NativeSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.destination = Path(self.temporary_directory.name)

    def test_extracts_regular_layer_content(self):
        from scripts.native_setup import safe_extract_layer

        safe_extract_layer(layer([
            ('src/', '', 'directory'),
            ('src/index.html', '<html/>', 'file'),
        ]), self.destination)

        self.assertEqual(
            (self.destination / 'src' / 'index.html').read_text(),
            '<html/>',
        )

    def test_whiteout_removes_file_from_earlier_layer(self):
        from scripts.native_setup import safe_extract_layer

        old = self.destination / 'src' / 'old.js'
        old.parent.mkdir()
        old.write_text('old')

        safe_extract_layer(layer([
            ('src/.wh.old.js', '', 'file'),
        ]), self.destination)

        self.assertFalse(old.exists())

    def test_rejects_path_traversal_and_absolute_paths(self):
        from scripts.native_setup import safe_extract_layer

        for name in ('../escape', '/absolute'):
            with self.subTest(name=name), self.assertRaises(NativeError):
                safe_extract_layer(layer([(name, 'bad', 'file')]),
                                   self.destination)

    def test_rejects_symlink_that_escapes_destination(self):
        from scripts.native_setup import safe_extract_layer

        with self.assertRaises(NativeError):
            safe_extract_layer(layer([
                ('src/outside', '../../outside', 'symlink'),
            ]), self.destination)

    def test_digest_mismatch_is_rejected(self):
        from scripts.native_setup import verify_digest

        with self.assertRaisesRegex(NativeError, 'digest mismatch'):
            verify_digest(b'payload', 'sha256:' + ('0' * 64))

    def test_layout_injection_requires_exactly_one_placeholder(self):
        from scripts.native_setup import inject_layout

        viewer = self.destination / 'viewer'
        viewer.mkdir()
        index = viewer / 'index.html'
        index.write_text(
            '<script>/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/</script>')
        layout = self.destination / 'layout.json'
        layout.write_text('{"name": "Indoor Navigation"}')

        inject_layout(viewer, layout)

        self.assertIn('Indoor Navigation', index.read_text())
        self.assertNotIn('PLACEHOLDER', index.read_text())
        with self.assertRaisesRegex(NativeError, 'exactly once'):
            inject_layout(viewer, layout)

    def test_direct_script_entry_point_can_import_local_helpers(self):
        result = subprocess.run(
            [sys.executable, 'scripts/native_setup.py', '--version'],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Pixi 0.69.0', result.stdout)

    def test_manifest_pins_setuptools_below_removed_develop_flags(self):
        manifest = (Path(__file__).resolve().parents[1] / 'experiments' /
                    'native-macos' / 'pixi.toml').read_text()
        self.assertIn('setuptools = "<80"', manifest)


if __name__ == '__main__':
    unittest.main()
