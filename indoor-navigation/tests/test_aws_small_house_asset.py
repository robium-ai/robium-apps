import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
FETCHER = APP_ROOT / 'scripts' / 'fetch_aws_small_house.py'
COMMIT = 'ff9631ca6d1db9c1ba656498151464b5ab74aafe'


def write_archive(path, members):
    prefix = f'aws-robomaker-small-house-world-{COMMIT}'
    with tarfile.open(path, 'w:gz') as archive:
        for relative_path, content in members.items():
            payload = content.encode()
            info = tarfile.TarInfo(f'{prefix}/{relative_path}')
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


class AwsSmallHouseAssetTests(unittest.TestCase):
    def test_fetcher_extracts_required_tree_and_records_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / 'house.tar.gz'
            destination = root / 'asset'
            write_archive(archive, {
                'LICENSE': 'MIT license fixture',
                'models/chair/model.sdf': '<sdf/>',
                'worlds/small_house.world': '<sdf/>',
            })

            result = subprocess.run([
                sys.executable, str(FETCHER),
                '--commit', COMMIT,
                '--archive-url', archive.as_uri(),
                '--destination', str(destination),
            ], capture_output=True, text=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (destination / 'worlds/small_house.world').read_text(), '<sdf/>')
            self.assertEqual(
                (destination / 'models/chair/model.sdf').read_text(), '<sdf/>')
            self.assertEqual((destination / 'LICENSE').read_text(), 'MIT license fixture')
            source = (destination / 'SOURCE').read_text()
            self.assertIn(COMMIT, source)
            self.assertIn('aws-robotics/aws-robomaker-small-house-world', source)

    def test_fetcher_rejects_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / 'unsafe.tar.gz'
            destination = root / 'asset'
            with tarfile.open(archive, 'w:gz') as bundle:
                payload = b'escape'
                info = tarfile.TarInfo('../outside')
                info.size = len(payload)
                bundle.addfile(info, io.BytesIO(payload))

            result = subprocess.run([
                sys.executable, str(FETCHER),
                '--commit', COMMIT,
                '--archive-url', archive.as_uri(),
                '--destination', str(destination),
            ], capture_output=True, text=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unsafe archive path', result.stderr)
            self.assertFalse((root / 'outside').exists())


if __name__ == '__main__':
    unittest.main()
