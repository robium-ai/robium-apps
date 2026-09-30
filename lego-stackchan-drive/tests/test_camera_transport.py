import http.client
import io

import pytest

from lego_stackchan_drive.camera import frames


@pytest.mark.parametrize('joined', [False, True])
def test_multipart_reader_is_independent_of_http_chunk_boundaries(monkeypatch, joined):
    jpeg = b'\xff\xd8wire-format-test\xff\xd9'
    header = (
        f'\r\n--frame\r\nContent-Length: {len(jpeg)}\r\nX-Sequence: 7\r\n'
        'X-Sensor-Us: 100\r\nX-Sent-Us: 200\r\nX-Target-Fps: 8\r\n'
        'X-Jpeg-Quality: 75\r\nX-Tcp-No-Delay: 1\r\nX-Network-Mode: ap\r\n\r\n'
    ).encode()
    chunks = [header + jpeg] if joined else [header, jpeg]
    wire = b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'
    for chunk in chunks:
        wire += f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n'
    wire += b'0\r\n\r\n'

    class Socket:
        def makefile(self, _mode):
            return io.BufferedReader(io.BytesIO(wire))

    response = http.client.HTTPResponse(Socket())
    response.begin()
    monkeypatch.setattr('urllib.request.urlopen', lambda *_args, **_kwargs: response)
    stream = frames('http://test/stream', 'test-key')
    try:
        event = next(stream)
        assert event['jpeg'] == jpeg and event['sequence'] == 7
        assert event['target_fps'] == 8 and event['jpeg_quality'] == 75
        assert event['tcp_no_delay'] == 1
        assert event['network_mode'] == 'ap' and 'rssi_dbm' not in event
    finally:
        stream.close()
