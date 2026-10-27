"""Heaps .pak read/write (hxd.fmt.pak). Layout, verified on res.compressed.pak:

'PAK' u8 version | u32 headerSize | u32 dataSize | root entry | zero pad | 'DATA' | data...
('DATA' occupies the last 4 header bytes; data starts at headerSize.)
entry: u8 nameLen, name, u8 flags (1=dir, 2=f64 pos) then
  dir:  u32 count, entries   file: pos (u32|f64, relative to headerSize), u32 size, u32 adler32
"""
import struct
import zlib


def read_index(path):
    """Return {path: (absolute_offset, size, adler32)}."""
    entries = {}
    with open(path, 'rb') as f:
        if f.read(4) != b'PAK\0':
            raise ValueError(f'{path}: not a PAK v0 archive')
        base, = struct.unpack('<I', f.read(4))
        f.read(4)  # data size; may wrap for >4GB archives

        def walk(parent, depth):
            if depth > 64 or f.tell() >= base:
                raise ValueError('invalid archive directory')
            name = f.read(f.read(1)[0]).decode('utf-8')
            flags = f.read(1)[0]
            full = '/'.join(filter(None, (parent, name)))
            if flags & 1:
                for _ in range(struct.unpack('<I', f.read(4))[0]):
                    walk(full, depth + 1)
            else:
                pos = struct.unpack('<d', f.read(8))[0] if flags & 2 else struct.unpack('<I', f.read(4))[0]
                size, check = struct.unpack('<II', f.read(8))
                entries[full] = (base + int(pos), size, check)

        walk('', 0)
        f.seek(base - 4)  # official packs zero-pad the header; 'DATA' always ends it
        if f.read(4) != b'DATA':
            raise ValueError('missing DATA marker')
    return entries


def read_file(path, name):
    offset, size, check = read_index(path)[name]
    with open(path, 'rb') as f:
        f.seek(offset)
        raw = f.read(size)
    if len(raw) != size or zlib.adler32(raw) != check:
        raise ValueError(f'{name}: checksum mismatch')
    return raw


def write(files):
    """files: {root-level name: bytes} -> pak bytes. Later packs override same-named files."""
    entries, data = b'', b''
    for name, raw in files.items():
        n = name.encode('utf-8')
        entries += bytes([len(n)]) + n + b'\0' + struct.pack('<III', len(data), len(raw), zlib.adler32(raw))
        data += raw
    root = b'\0\1' + struct.pack('<I', len(files)) + entries
    header_size = 12 + len(root) + 4
    return b'PAK\0' + struct.pack('<II', header_size, len(data)) + root + b'DATA' + data
