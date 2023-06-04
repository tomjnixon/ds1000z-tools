import warnings
import pyvisa
import re
from typing import Optional


def get_pmap_message() -> tuple[bytes, int]:
    """get a VXI-11 and rfc1050 PMAPPROC_GETPORT message body, and the port to
    send it to
    """
    # if this breaks because of pyvisa_py internal changes (which would be
    # reasonable), just hard-code the message like in liblxi
    from pyvisa_py.protocols.rpc import (
        AuthorizationFlavor,
        IPPROTO_TCP,
        PMAP_PORT,
        PortMapperPacker,
        PortMapperVersion,
    )
    from pyvisa_py.protocols.vxi11 import (
        DEVICE_CORE_PROG,
        DEVICE_CORE_VERS,
    )

    # rfc1050 says:
    #
    #     Given a program number "prog", version number "vers", and
    #     transport protocol number "prot", this procedure returns the
    #     port number on which the program is awaiting call requests.  A
    #     port value of zeros means the program has not been registered.
    #     The "port" field of the argument is ignored.
    #
    # VXI-11 rule RULE B.6.1 specifies the program and version
    #
    # see also:
    # https://github.com/lxi-tools/liblxi/blob/32cc51b0bf1ca334c97702f3a43bb64551cf988c/src/vxi11.c#L451
    # https://github.com/python-ivi/python-vxi11/blob/cc4671da699f1f379137dc40ffc4a302d72e6f55/vxi11/vxi11.py#L501-L521

    proc = PortMapperVersion.get_port
    mapping = (DEVICE_CORE_PROG, DEVICE_CORE_VERS, IPPROTO_TCP, 0)

    xid = 0
    cred = verf = (AuthorizationFlavor.null, b"")

    packer = PortMapperPacker()
    packer.pack_callheader(xid, DEVICE_CORE_PROG, DEVICE_CORE_VERS, proc, cred, verf)
    packer.pack_mapping(mapping)

    return packer.get_buf(), PMAP_PORT


def try_addr(
    rm: pyvisa.ResourceManager, addr: str, idn_pattern: str
) -> Optional[pyvisa.Resource]:
    """try connecting to an instrument at addr; if we can connect and the IDN
    string matches idn_pattern, return it
    """

    visa_addr = f"TCPIP::{addr}::INSTR"

    try:
        resource = rm.open_resource(visa_addr)
        idn_str = resource.query("*IDN?")
        if re.search(idn_pattern, idn_str) is not None:
            return resource
        resource.close()

    except (pyvisa.VisaIOError, OSError):
        pass
    except Exception as e:
        warnings.warn(f"unknown exception type while trying to open {visa_addr}: {e}")


def discover(rm: pyvisa.ResourceManager, idn_pattern: str) -> Optional[pyvisa.Resource]:
    """find the first VXI-11 instrument whose "*IDN?" string matches the
    idn_pattern regex

    this uses broadcast rfc1050 PMAPPROC_GETPORT messages rather than avahi;
    see get_pmap_message. the response is not parsed; it's possible, but it
    only contains the port, which is trickky to use with pyvisa
    """
    import socket
    import select
    import time

    message, port = get_pmap_message()
    addr = "<broadcast>"

    BUFSIZE = 1500

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # send 'loops' times, each time waiting 'timeout' seconds
        loops = 3
        timeout = 0.5

        seen = set()

        for i in range(loops):
            sock.sendto(message, (addr, port))

            loop_end = time.time() + timeout
            while (now := time.time()) < loop_end:
                r, w, x = select.select([sock], [], [], loop_end - now)

                if sock in r:
                    reply, (fromaddr, fromport) = sock.recvfrom(BUFSIZE)

                    if fromaddr in seen:
                        continue
                    seen.add(fromaddr)

                    resource = try_addr(rm, fromaddr, idn_pattern)
                    if resource is not None:
                        return resource
                else:
                    break  # timeout


if __name__ == "__main__":
    rm = pyvisa.ResourceManager()

    res = discover(rm, "RIGOL TECHNOLOGIES,DS1...Z")
    print(res)
