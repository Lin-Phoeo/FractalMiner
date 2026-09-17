"""Send one command to the installed Unity MCP loopback bridge (port 6400)."""
import json
import socket
import struct
import sys


def exact(stream, size):
    result = bytearray()
    while len(result) < size:
        chunk = stream.recv(size-len(result))
        if not chunk:
            raise ConnectionError("Unity closed the connection")
        result.extend(chunk)
    return bytes(result)


with socket.create_connection(("127.0.0.1", 6400), timeout=60) as stream:
    welcome = bytearray()
    while not welcome.endswith(b"\n"):
        welcome.extend(exact(stream, 1))
    command = {"type": "execute_code", "params": {"action": "execute", "code": sys.argv[1], "safety_checks": True}}
    payload = json.dumps(command).encode("utf-8")
    stream.sendall(struct.pack(">Q", len(payload)) + payload)
    length = struct.unpack(">Q", exact(stream, 8))[0]
    print(exact(stream, length).decode("utf-8"))
