import socket
import logging

DEFAULT_RESOURCE_PATTERN = "TCPIP::{addr}::5555::SOCKET"
DEFAULT_IDN_PATTERN = "RIGOL TECHNOLOGIES,DS1...Z"


def fixup_resource(resource):
    """fiddle with resource to make it work properly with DS1000Z scopes"""
    resource.read_termination = "\n"
    resource.write_termination = "\n"
    resource.chunk_size = 1000000

    if resource.visalib.library_path == "py":
        from pyvisa_py.tcpip import TCPIPInstrVxi11, TCPIPSocketSession

        session = resource.visalib.sessions[resource.session]

        # pyvisa_py uses the received maxRecvSize value (as max_recv_size)
        # to limit the message response size, but the VXI-11 spec says that
        # maxRecvSize "specifies max data size in bytes device will accept
        # on a write" we're not going to write anything big, so it's ok to
        # increase this manually. this avoids splitting up reads into
        # 1500-byte chunks, which massively increases the number of
        # round-trips
        if isinstance(session, (TCPIPInstrVxi11, TCPIPSocketSession)):
            try:
                session.max_recv_size = 1000000
            except:  # noqa
                logging.warn("failed to set max_recv_size")

        # TCP_NODELAY helps, which makes sense for RPC
        try:
            if isinstance(session, TCPIPInstrVxi11):
                session.interface.sock.setsockopt(
                    socket.IPPROTO_TCP, socket.TCP_NODELAY, 1
                )
            elif isinstance(session, TCPIPSocketSession):
                session.interface.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except:  # noqa
            logging.warn("failed to set TCP_NODELAY")
