"""Byte-preserving archives with content-bound, integrity-checked source maps."""
import datetime
import hashlib
import json
import os
import uuid


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _map_digest(crumbs):
    return digest(json.dumps(crumbs, ensure_ascii=True, separators=(',', ':')).encode('utf-8'))


def _metadata_digest(data):
    bound = {k: v for k, v in data.items() if k != 'metadata_sha256'}
    return digest(json.dumps(bound, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8'))


def _reject_constant(value):
    raise ValueError(f'non-finite metadata constant: {value}')


def inspect_archive(path, raw=None):
    """Legacy sidecars remain readable but cannot prove source-map/content binding."""
    raw = path.read_bytes() if raw is None else raw
    result = {'status': 'missing', 'content_sha256': digest(raw), 'issues': [], 'metadata': None}
    try:
        data = json.loads(path.with_suffix('.meta.json').read_text(encoding='utf-8'), parse_constant=_reject_constant)
    except FileNotFoundError:
        return result
    except (OSError, ValueError, RecursionError):
        return dict(result, status='invalid', issues=['unreadable archive metadata'])
    if not isinstance(data, dict):
        return dict(result, status='invalid', issues=['metadata must be an object'])
    result['metadata'] = data
    if data.get('format') in (None, 1, 2):
        return dict(result, status='legacy_unbound', issues=['legacy metadata has no verified content binding'])
    if type(data.get('format')) is not int or data['format'] != 3:
        return dict(result, status='invalid', issues=['unsupported archive metadata format'])
    errors = result['issues']
    try:
        metadata_hash = _metadata_digest(data)
    except (ValueError, TypeError, RecursionError):
        return dict(result, status='invalid', issues=['unsupported metadata value'])
    if data.get('metadata_sha256') != metadata_hash:
        errors.append('archive metadata does not match its recorded digest')
    if (data.get('content_sha256') != result['content_sha256'] or type(data.get('content_bytes')) is not int
            or data.get('content_bytes') != len(raw)):
        errors.append('log content does not match its archive metadata')
    crumbs = data.get('crumbs')
    if crumbs is not None:
        if not isinstance(crumbs, list) or not all(isinstance(line, str) for line in crumbs):
            errors.append('source map must be a list of source locations')
        elif data.get('crumbs_sha256') != _map_digest(crumbs):
            errors.append('source map does not match its recorded digest')
    if not isinstance(data.get('source_map_matches_build'), bool):
        errors.append('source-map provenance flag missing or invalid')
    result['status'] = 'mismatch' if errors else 'verified'
    return result


def _atomic_write(path, data):
    temp = path.with_name(f'{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def archive(source, directory, metadata):
    raw = source.encode('utf-8') if isinstance(source, str) else source
    content_hash = digest(raw)
    directory.mkdir(parents=True, exist_ok=True)
    for existing in sorted(directory.glob(f'*-{content_hash[:10]}.log')):
        checked = inspect_archive(existing)
        if checked['status'] == 'verified' and checked['content_sha256'] == content_hash:
            return existing  # a later build must never replace a verified source map
    crumbs = metadata.get('crumbs')
    if crumbs is not None and (not isinstance(crumbs, list) or not all(isinstance(line, str) for line in crumbs)):
        raise ValueError('source map must be a list of source locations')
    if not isinstance(metadata.get('source_map_matches_build', False), bool):
        raise ValueError('source-map provenance flag must be true or false')
    record = {**metadata, 'format': 3, 'content_sha256': content_hash, 'content_bytes': len(raw),
              'crumbs_sha256': _map_digest(crumbs) if crumbs is not None else None,
              'source_map_matches_build': metadata.get('source_map_matches_build', False)}
    record['metadata_sha256'] = _metadata_digest(record)
    encoded = (json.dumps(record, indent=2, allow_nan=False) + '\n').encode('utf-8')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    path = directory / f'{stamp}-{uuid.uuid4().hex[:8]}-{content_hash[:10]}.log'
    _atomic_write(path, raw)
    _atomic_write(path.with_suffix('.meta.json'), encoded)
    return path


def source_map(path, inspection=None):
    checked = inspect_archive(path) if inspection is None else inspection
    if checked['status'] != 'verified':
        return None
    data = checked['metadata']
    return data.get('crumbs') if data.get('source_map_matches_build') is True else None
