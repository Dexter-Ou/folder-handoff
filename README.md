# Folder Handoff — offline preview

Create a SHA-256 inventory of a stopped folder, then check a delivered copy for
missing, changed and extra files. Uses Python 3.10+ standard library; no account,
network or installation. This preview is intended for trusted local directories.
It reads files; it never repairs or deletes them.

Keep the manifest **outside** the inventoried directory. Choose a new manifest
filename and enable shell no-clobber before redirecting output:

```sh
set -C
python3 handoff.py create ./original > ./handoff-manifest.json
python3 handoff.py verify ./delivered --manifest ./handoff-manifest.json
```

Create returns 0 on completion. Verify returns 0 when file paths, sizes and hashes
match, 1 for differences, and 2 for refused input or an I/O error. Verify emits
JSON lists `missing`, `extra`, `changed` and boolean `matches`. Never treat status
2 as a match. Preserve diagnostics and remove an incomplete manifest only after
review; shell redirection can leave an empty file on failure. Do not redirect
onto an existing file or into either folder.

Limits: 10,000 files, 1 GiB total file bytes, 4 MiB manifest. Empty directories,
permissions, timestamps and extended attributes are not compared. Symlinks and
special files are refused. Names are case-sensitive and use `/` separators in
manifests. Hashes provide consistency, not sender authenticity: get the manifest
through a trusted channel. A maliciously replaced manifest can approve altered
files. Manifests disclose filenames, sizes and hashes; keep private ones private.

Stop all writers before both operations. Some mid-read changes are detected,
but this is not an atomic filesystem snapshot, hostile-directory defense, backup,
or crash-durability guarantee. No restore function exists. Cross-platform and
Python 3.10 behavior remain untested until separately recorded.
