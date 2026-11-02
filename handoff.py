#!/usr/bin/env python3
"""Offline folder inventory and verification for trusted, stopped directories."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

MAX_FILES = 10000
MAX_BYTES = 1024 * 1024 * 1024
MAX_MANIFEST = 4 * 1024 * 1024

class Refusal(Exception):
    pass

def inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise Refusal('root must be a real directory')
    entries = []
    total = 0
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise Refusal('symlinks are unsupported')
        for name in files:
            p = Path(directory) / name
            if not stat.S_ISREG(p.lstat().st_mode):
                raise Refusal('only regular files are supported')
            if len(entries) >= MAX_FILES:
                raise Refusal('file limit exceeded')
            before = p.stat()
            total += before.st_size
            if total > MAX_BYTES:
                raise Refusal('total byte limit exceeded')
            digest = hashlib.sha256()
            count = 0
            with p.open('rb') as stream:
                while True:
                    block = stream.read(65536)
                    if not block:
                        break
                    count += len(block)
                    if count > before.st_size:
                        raise Refusal('file changed while reading')
                    digest.update(block)
            after = p.stat()
            if count != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise Refusal('file changed while reading')
            entries.append({'path': p.relative_to(root).as_posix(), 'bytes': count, 'sha256': digest.hexdigest()})
    return sorted(entries, key=lambda x: x['path'])

def load_manifest(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_MANIFEST + 1)
    if len(raw) > MAX_MANIFEST:
        raise Refusal('manifest byte limit exceeded')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refusal('duplicate JSON field')
            result[key] = value
        return result
    m = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(m, dict) or set(m) != {'version', 'files'} or type(m['version']) is not int or m['version'] != 1 or not isinstance(m['files'], list) or len(m['files']) > MAX_FILES:
        raise Refusal('unsupported manifest schema')
    seen = set()
    total = 0
    for e in m['files']:
        if not isinstance(e, dict) or set(e) != {'path', 'bytes', 'sha256'}:
            raise Refusal('invalid file entry')
        p, size, digest = e['path'], e['bytes'], e['sha256']
        if not isinstance(p, str) or not p or '\\' in p or '\x00' in p or PurePosixPath(p).is_absolute() or any(x in ('', '.', '..') for x in p.split('/')) or p in seen:
            raise Refusal('invalid or repeated path')
        if type(size) is not int or size < 0 or not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise Refusal('invalid size or digest')
        total += size
        if total > MAX_BYTES:
            raise Refusal('total byte limit exceeded')
        seen.add(p)
    return m['files']

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('operation', choices=['create', 'verify'])
    parser.add_argument('directory')
    parser.add_argument('--manifest')
    args = parser.parse_args(argv)
    if (args.operation == 'verify') != bool(args.manifest):
        parser.error('verify requires --manifest; create does not accept it')
    try:
        expected = load_manifest(args.manifest) if args.operation == 'verify' else None
        actual = inventory(args.directory)
        if expected is None:
            result, status = {'version': 1, 'files': actual}, 0
        else:
            old = {e['path']: e for e in expected}
            new = {e['path']: e for e in actual}
            result = {'missing': sorted(old.keys() - new.keys()), 'extra': sorted(new.keys() - old.keys()), 'changed': sorted(p for p in old.keys() & new.keys() if old[p] != new[p])}
            result['matches'] = not any(result.values())
            status = 0 if result['matches'] else 1
        encoded = json.dumps(result, ensure_ascii=True, indent=2)
        if expected is None and len((encoded + '\n').encode('utf-8')) > MAX_MANIFEST:
            raise Refusal('generated manifest byte limit exceeded')
        print(encoded)
        return status
    except (OSError, ValueError, RecursionError, Refusal):
        print('handoff: refused; check trusted paths, format, limits and stopped writers', file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
