# -*- coding: utf-8 -*-
"""Extract Model node names from binary FBX (Kaydara format), robust parser."""
import struct, sys, io

def read_prop(f):
    tc = f.read(1)
    if tc == b'S':
        ln = struct.unpack('<I', f.read(4))[0]
        return f.read(ln).decode('utf-8', 'replace')
    if tc == b'R':
        ln = struct.unpack('<I', f.read(4))[0]
        return f.read(ln)
    if tc == b'L': return struct.unpack('<q', f.read(8))[0]
    if tc == b'I': return struct.unpack('<i', f.read(4))[0]
    if tc == b'D': return struct.unpack('<d', f.read(8))[0]
    if tc == b'F': return struct.unpack('<f', f.read(4))[0]
    if tc == b'C': return f.read(1)
    if tc in (b'f', b'd', b'l', b'i', b'b'):
        alen, enc, clen = struct.unpack('<III', f.read(12))
        f.read(clen)
        return ('arr', alen)
    raise ValueError(f'bad type {tc!r} @ {f.tell()-1}')

def parse(f, end, version, out):
    hdrlen = 32 if version >= 7500 else 25
    nulllen = 25 if version >= 7500 else 13
    while True:
        pos = f.tell()
        if pos + nulllen > end:
            return
        peek = f.read(nulllen)
        if peek == b'\x00' * nulllen:
            return  # end of nesting level
        f.seek(pos)
        hdr = f.read(hdrlen)
        if len(hdr) < hdrlen:
            return
        if version >= 7500:
            eoff, nprop, plen = struct.unpack('<QII', hdr[:16])
            namelen = hdr[16]
            name = hdr[17:17+namelen].decode('utf-8', 'replace')
        else:
            eoff, nprop, plen = struct.unpack('<III', hdr[:12])
            namelen = hdr[12]
            name = hdr[13:13+namelen].decode('utf-8', 'replace')
        if eoff <= 0 or eoff > end:
            return
        props = []
        try:
            for _ in range(nprop):
                props.append(read_prop(f))
        except Exception:
            f.seek(eoff)
            continue
        if name == 'Model':
            nm = props[1].split('\x00')[0] if len(props) > 1 and isinstance(props[1], str) else '?'
            sub = props[2] if len(props) > 2 and isinstance(props[2], str) else ''
            out.append((sub, nm))
        if eoff - f.tell() > nulllen:
            parse(f, eoff, version, out)
        f.seek(eoff)

data = open(sys.argv[1], 'rb').read()
version = struct.unpack('<I', data[23:27])[0]
print(f'# FBX version {version}', file=sys.stderr)
f = io.BytesIO(data)
f.seek(27)
out = []
parse(f, len(data), version, out)
for sub, nm in out:
    print(f'{sub}\t{nm}')
