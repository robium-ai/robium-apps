import json
import subprocess

import pytest

from lego_stackchan_drive import direct_wifi


def recovery_fixture(tmp_path):
    (tmp_path / '.local').mkdir()
    session = tmp_path / 'session'
    session.mkdir()
    direct_wifi.write_private(tmp_path / '.local/wifi.json',
                              {'ssid': 'home', 'password': 'private-home-password'})
    before = {'url': 'http://10.0.0.35/stream', 'key': 'private-stream-key'}
    direct_wifi.write_private(session / 'camera-before.json', before)
    direct_wifi.write_private(tmp_path / '.local/camera.json',
                              {**before, 'url': 'http://192.168.4.1/stream'})
    direct_wifi.write_private(session / 'state.json',
                              {'interface': 'en0', 'port': 'fake', 'restored': False})
    return session, before


def test_wifi_password_uses_stdin_not_process_arguments(monkeypatch):
    seen = {}

    def run(args, **kwargs):
        seen.update(args=args, kwargs=kwargs)
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(direct_wifi.subprocess, 'run', run)
    direct_wifi.join_wifi('en0', 'test-ap', 'private-password')
    assert 'private-password' not in seen['args']
    assert seen['args'][-1] == '-'
    assert seen['kwargs']['input'] == 'private-password\n'


def test_recovery_restores_internet_even_if_camera_usb_is_lost(tmp_path, monkeypatch):
    session, before = recovery_fixture(tmp_path)
    joined = []
    monkeypatch.setattr(direct_wifi, 'join_wifi', lambda *args: joined.append(args))

    def lost_usb(*_args, **_kwargs):
        raise OSError('disconnected')

    monkeypatch.setattr(direct_wifi, 'device_request', lost_usb)
    with pytest.raises(RuntimeError, match='station recovery'):
        direct_wifi.restore_home(tmp_path, session)
    assert joined == [('en0', 'home', 'private-home-password')]
    assert json.loads((tmp_path / '.local/camera.json').read_text()) == before
    assert not json.loads((session / 'state.json').read_text())['restored']


def test_recovery_restores_camera_config_even_if_mac_join_fails(tmp_path, monkeypatch):
    session, before = recovery_fixture(tmp_path)

    def failed_join(*_args):
        raise RuntimeError('cannot join')

    monkeypatch.setattr(direct_wifi, 'join_wifi', failed_join)
    monkeypatch.setattr(direct_wifi, 'device_request',
                        lambda *_args: {'network_mode': 'ap', 'status': 'saved'})
    monkeypatch.setattr(direct_wifi, 'wait_device', lambda *_args: {'ip': '10.0.0.36'})
    with pytest.raises(RuntimeError, match='Mac home Wi-Fi'):
        direct_wifi.restore_home(tmp_path, session)
    restored = json.loads((tmp_path / '.local/camera.json').read_text())
    assert restored == {**before, 'url': 'http://10.0.0.36/stream'}


def test_recovery_is_idempotent_after_confirmed_restore(tmp_path, monkeypatch):
    session, _ = recovery_fixture(tmp_path)
    joined = []
    monkeypatch.setattr(direct_wifi, 'join_wifi', lambda *args: joined.append(args))
    monkeypatch.setattr(direct_wifi, 'device_request', lambda *_args: {'network_mode': 'station'})
    monkeypatch.setattr(direct_wifi, 'wait_device', lambda *_args: {'ip': '10.0.0.35'})
    direct_wifi.restore_home(tmp_path, session)
    direct_wifi.restore_home(tmp_path, session)
    assert len(joined) == 1
    assert json.loads((session / 'state.json').read_text())['restored']


def test_internet_check_rejects_wifi_default_before_any_probe(monkeypatch):
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, 'interface: en0\n', '')

    monkeypatch.setattr(direct_wifi.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='default route'):
        direct_wifi.verify_internet('en7')
    assert len(calls) == 1


def test_preflight_uses_http_without_opening_usb_or_changing_network(tmp_path, monkeypatch):
    (tmp_path / '.local').mkdir()
    direct_wifi.write_private(tmp_path / '.local/camera.json',
                              {'url': 'http://192.168.4.1/stream', 'key': 'private-key'})
    monkeypatch.setattr(direct_wifi.sys, 'argv', ['direct_wifi', '--root', str(tmp_path)])
    monkeypatch.setattr(direct_wifi, 'camera_status', lambda _config: {'network_mode': 'ap'})

    def unexpected(*_args, **_kwargs):
        pytest.fail('Read-only preflight attempted a USB or network mutation')

    monkeypatch.setattr(direct_wifi, 'device_request', unexpected)
    monkeypatch.setattr(direct_wifi, 'join_wifi', unexpected)
    direct_wifi.main()
