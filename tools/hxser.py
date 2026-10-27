"""Minimal haxe.Serializer format + hxd.Save checksum, enough for prefs.sav.

Round-trips the game's prefs byte-for-byte (string cache 'R' refs are reproduced).
Supported: n t f z i d k m p y R o..g a..h u b..h (StringMap). Floats keep their text.
"""
import hashlib
from urllib.parse import quote, unquote

SALT = 's*al!t'  # hxd.Save.SALT (Heaps default, verified against prefs.sav)


class HxFloat(str):
    """Float kept as its serialized text so round trips are exact."""


class HxStringMap(dict):
    pass


def _sha1(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def make_crc(data):
    return _sha1(data + _sha1(data + SALT))[4:36]


def load_save(text):
    data, sep, crc = text.rpartition('#')
    if not sep or make_crc(data) != crc:
        raise ValueError('prefs checksum mismatch')
    return loads(data)


def dump_save(value):
    data = dumps(value)
    return data + '#' + make_crc(data)


def loads(s):
    pos = 0
    cache = []

    def num():
        nonlocal pos
        start = pos
        while pos < len(s) and (s[pos].isdigit() or s[pos] in '-+.eE'):
            pos += 1
        return s[start:pos]

    def string():
        nonlocal pos
        tag = s[pos]
        pos += 1
        if tag == 'R':
            return cache[int(num())]
        if tag != 'y':
            raise ValueError(f'expected string at {pos - 1}')
        length = int(num())
        pos += 1  # ':'
        raw = s[pos:pos + length]
        pos += length
        value = unquote(raw)
        cache.append(value)
        return value

    def value():
        nonlocal pos
        tag = s[pos]
        if tag in 'yR':
            return string()
        pos += 1
        if tag == 'n': return None
        if tag == 't': return True
        if tag == 'f': return False
        if tag == 'z': return 0
        if tag == 'i': return int(num())
        if tag == 'd': return HxFloat(num())
        if tag in 'kmp': return HxFloat({'k': 'NaN', 'm': '-Inf', 'p': 'Inf'}[tag])
        if tag == 'o':
            obj = {}
            while s[pos] != 'g':
                key = string()
                obj[key] = value()
            pos += 1
            return obj
        if tag == 'a':
            arr = []
            while s[pos] != 'h':
                if s[pos] == 'u':
                    pos += 1
                    arr.extend([None] * int(num()))
                else:
                    arr.append(value())
            pos += 1
            return arr
        if tag == 'b':
            m = HxStringMap()
            while s[pos] != 'h':
                key = string()
                m[key] = value()
            pos += 1
            return m
        raise ValueError(f'unsupported haxe tag {tag!r} at {pos - 1}')

    result = value()
    if pos != len(s):
        raise ValueError('trailing data in serialized value')
    return result


def dumps(v):
    out = []
    cache = {}

    def string(x):
        if x in cache:
            out.append(f'R{cache[x]}')
            return
        cache[x] = len(cache)
        enc = quote(x, safe="-_.!~*'()")
        out.append(f'y{len(enc)}:{enc}')

    def value(x):
        if x is None: out.append('n')
        elif x is True: out.append('t')
        elif x is False: out.append('f')
        elif isinstance(x, HxFloat):
            out.append({'NaN': 'k', '-Inf': 'm', 'Inf': 'p'}.get(x, 'd' + x))
        elif isinstance(x, float): out.append('d' + repr(x))
        elif isinstance(x, int): out.append('z' if x == 0 else f'i{x}')
        elif isinstance(x, str): string(x)
        elif isinstance(x, HxStringMap):
            out.append('b')
            for k, item in x.items():
                string(k)
                value(item)
            out.append('h')
        elif isinstance(x, dict):
            out.append('o')
            for k, item in x.items():
                string(k)
                value(item)
            out.append('g')
        elif isinstance(x, list):
            out.append('a')
            nulls = 0
            for item in x:
                if item is None:
                    nulls += 1
                    continue
                if nulls:
                    out.append('n' if nulls == 1 else f'u{nulls}')
                    nulls = 0
                value(item)
            if nulls:
                out.append('n' if nulls == 1 else f'u{nulls}')
            out.append('h')
        else:
            raise TypeError(f'cannot serialize {type(x).__name__}')

    value(v)
    return ''.join(out)
