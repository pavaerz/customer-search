"""Read historical reports after archival, without extracting into the repository."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read_text(path, root=ROOT):
    root = Path(root).resolve()
    path = Path(path)
    path = path if path.is_absolute() else root / path
    relative = path.resolve().relative_to(root).as_posix()
    if path.exists():
        return path.read_text(encoding='utf-8')
    archive = root / 'archives/customersearch-analysis-archive.zip'
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read('ARCHIVE-MANIFEST.json'))
        entry = next((e for e in manifest['files'] if e['path'] == relative), None)
        if entry is None:
            raise FileNotFoundError(relative)
        data = z.read(relative)
        if hashlib.sha256(data).hexdigest() != entry['archived_sha256']:
            raise ValueError('Historical analysis checksum mismatch')
        return data.decode('utf-8')
