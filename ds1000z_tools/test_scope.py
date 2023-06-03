from unittest.mock import Mock
import pytest
from .scope import DS1000Z, Preamble, WavFormat, WavType
import re
import numpy as np


class MockResource(Mock):
    """basic mock of pyvisa resource with methods to write, read and query

    to use this, define _write(cmd) in a subclass, which should call _send
    and/or _send_bytes to send the respoonse to the given command

    ideally we would be able to use pyvisa-sim for this, but it only really
    supports commands which always return the same thing
    """

    def __init__(self):
        super(MockResource, self).__init__()

        self.visalib.library_path.return_value = "mock"

        self.write.side_effect = self._write
        self.read.side_effect = self._read
        self.read_bytes.side_effect = self._read_bytes

        self.buf = bytearray()

    def _get_child_mock(self, **kw):
        return Mock(**kw)

    def query(self, cmd):
        self.write(cmd)
        return self.read()

    def _send(self, resp):
        self.buf.extend(resp.encode("ascii"))
        self.buf.extend(b"\n")

    def _send_bytes(self, resp):
        self.buf.extend(resp)

    def _read(self):
        assert b"\n" in self.buf, "read with nothing in buffer"
        resp, rest = self.buf.split(b"\n", 1)
        self.buf = rest
        return resp.decode("ascii")

    def _read_bytes(self, n):
        assert len(self.buf) >= n
        resp = bytes(self.buf[:n])
        self.buf = self.buf[n:]
        return resp


class MockDS1000ZResource(MockResource):
    """mock pyvisa Resource compatible with DS1000Z"""

    def _write(self, cmd):
        if cmd == "*IDN?":
            self._send("MOCK")

        elif cmd.startswith(":DISPlay:DATA? "):
            self._send_bytes(f"#9{len(self.display_data):09}".encode("ascii"))
            self._send_bytes(self.display_data)
            self._send_bytes(b"\n")

        elif cmd.startswith(":TRIGger:STATus?"):
            self._send(self.status)

        elif (match := re.fullmatch(r":(\w+):DISPlay\?", cmd)) is not None:
            self._send(str(int(match.group(1) in self.channel_data)))

        elif cmd.startswith(":WAVeform:MODE "):
            pass

        elif cmd.startswith(":WAVeform:FORMat "):
            pass

        elif (match := re.fullmatch(r":WAVeform:SOURce (\w+)", cmd)) is not None:
            self.wav_source = match.group(1)

        elif cmd == ":WAVeform:PREamble?":
            self._send(self.channel_data[self.wav_source]["preamble"])

        elif (match := re.fullmatch(r":WAVeform:STARt (\d+)", cmd)) is not None:
            self.wav_start = int(match.group(1))

        elif (match := re.fullmatch(r":WAVeform:STOP (\d+)", cmd)) is not None:
            self.wav_stop = int(match.group(1))

        elif cmd.startswith(":WAVeform:DATA?"):
            full_data = self.channel_data[self.wav_source]["data"]
            data = full_data[self.wav_start - 1 : self.wav_stop]

            self._send_bytes(f"#9{len(data):09}".encode("ascii"))
            self._send_bytes(data.tobytes())
            self._send_bytes(b"\n")

        else:
            assert False, f"unknown command: {cmd!r}"


@pytest.fixture
def scope():
    return DS1000Z(MockDS1000ZResource())


def test_init(scope):
    assert scope.resource.read_termination == "\n"
    assert scope.resource.write_termination == "\n"
    assert scope.resource.chunk_size == 1000000


def test_mock(scope):
    assert scope.resource.query("*IDN?") == "MOCK"
    assert scope.resource.write.called_with("*IDN?")


def test_screenshot(scope):
    scope.resource.display_data = b"abcde"

    result = scope.get_screenshot(format="PNG", color=True, invert=False)

    assert result == scope.resource.display_data

    assert scope.resource.write.called_with(":DISPlay:DATA? PNG,ON,OFF")


def do_test_get_data(scope, screen=False):
    if screen:
        n_points = 1000
        type = WavType.NORM
    else:
        n_points = 300000
        type = WavType.RAW

    chan1_data = np.random.randint(0, 256, size=n_points, dtype=np.uint8)
    scope.resource.channel_data = dict(
        CHAN1=dict(
            preamble=f"0,{type.value},{n_points},1,1.000000e-09,-3.000000e-03,0,4.132813e-01,0,122",
            data=chan1_data,
        ),
    )

    if screen:
        data = scope.get_data_screen()
    else:
        data = scope.get_data_memory()
    assert set(data.keys()) == {"CHAN1"}
    assert data["CHAN1"][0] == Preamble(
        format=WavFormat.BYTE,
        type=type,
        points=n_points,
        count=1,
        xincrement=1e-9,
        xorigin=-3e-3,
        xreference=0,
        yincrement=4.132813e-01,
        yorigin=0.0,
        yreference=122,
    )
    np.testing.assert_equal(data["CHAN1"][1], chan1_data)

    scope.resource.write.assert_any_call(":CHAN1:DISPlay?")
    scope.resource.write.assert_any_call(":CHAN2:DISPlay?")
    scope.resource.write.assert_any_call(":CHAN3:DISPlay?")
    scope.resource.write.assert_any_call(":CHAN4:DISPlay?")
    scope.resource.write.assert_any_call(":TRIGger:STATus?")
    scope.resource.write.assert_any_call(f":WAVeform:MODE {type.name}")
    scope.resource.write.assert_any_call(":WAVeform:FORMat BYTE")


def test_data_memory(scope):
    scope.resource.status = "STOP"

    do_test_get_data(scope, screen=False)


def test_data_screen(scope):
    scope.resource.status = "STOP"

    do_test_get_data(scope, screen=True)
