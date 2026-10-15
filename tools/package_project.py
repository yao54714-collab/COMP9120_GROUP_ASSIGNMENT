"""Create a team source handoff using an explicit allowlist, without local data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP = ['README.md', 'AI_SETUP.md', 'run.py', '.env.example', '.gitignore',
       'PawCare.code-workspace', 'requirements.txt', 'requirements-lock.txt']
GLOBS = ['.vscode/*.json', 'backend/*.py', 'database/*.sql', 'docs/*.md', 'docs/*.json',
         'frontend/src/**/*.tsx', 'frontend/src/**/*.ts', 'frontend/src/**/*.css',
         'frontend/src/**/*.svg', 'frontend/src/**/*.png', 'frontend/src/**/*.webp',
         'frontend/*.json', 'frontend/*.ts', 'frontend/index.html',
         'tests/*.py', 'tests/browser/*.ts', 'tools/*.py']
EVIDENCE = ['fixed-backend.xml', 'browser.json', 'fix-verification.json',
            'english-backend.xml', 'english-data-verification.json', 'package-verification.json',
            'english-user-accounts.png', 'english-login.png', 'powershell-verification.json',
            'audit-backend.xml', 'audit-browser-before-fixes.json',
            'audit-cat-booking-mobile.png', 'audit-cat-paid.png', 'audit-wrong-pet.png',
            'audit-hidden-filter.png', 'fixed-disabled-consumable-warning.png',
            'customer-desktop.png', 'customer-mobile.png', 'manager-desktop.png', 'manager-mobile.png']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'output/PawCare-team.zip')
    args = parser.parse_args()
    output = args.output.resolve()
    files = {ROOT / p for p in TOP}
    for pattern in GLOBS:
        files.update(ROOT.glob(pattern))
    files.update(ROOT / 'test-results' / p for p in EVIDENCE if (ROOT / 'test-results' / p).exists())
    files = sorted(files)
    secrets = []
    if (ROOT / '.env').exists():
        for line in (ROOT / '.env').read_text('utf-8-sig').splitlines():
            key, _, value = line.partition('=')
            if 'PASSWORD' in key.upper() and len(value.strip()) >= 12:
                secrets.append(value.strip().strip('\"\'').encode())
    private = ROOT / '.runtime/postgres-admin.json'
    if private.exists():
        secrets += [v.encode() for k, v in json.loads(private.read_text('utf-8')).items()
                    if 'password' in k and isinstance(v, str)]
    content = {}
    manifest = []
    forbidden = {'.runtime', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'dist', '.git'}
    for path in files:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError('Invalid package path: ' + str(path))
        relative = path.relative_to(ROOT)
        if forbidden.intersection(relative.parts) or path.name in {'.env', 'pgadmin-servers.json'}:
            raise RuntimeError('Private/generated file refused: ' + relative.as_posix())
        data = path.read_bytes()
        private_key_marker = b'-----BEGIN ' + b'PRIVATE KEY-----'
        if any(secret in data for secret in secrets) or private_key_marker in data:
            raise RuntimeError('Local secret detected in: ' + relative.as_posix())
        name = 'pawcare/' + relative.as_posix()
        content[name] = data
        manifest.append({'path': relative.as_posix(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    content['pawcare/PACKAGE_MANIFEST.json'] = json.dumps({
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'description': 'Windows team source handoff; no local credentials or database files.',
        'files': manifest}, ensure_ascii=False, indent=2).encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in content.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for entry in manifest:
            assert hashlib.sha256(archive.read('pawcare/' + entry['path'])).hexdigest() == entry['sha256']
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(digest + '  ' + output.name + '\n', 'utf-8')
    print('Package:', output)
    print('Files:', len(content), 'Bytes:', output.stat().st_size)
    print('SHA256:', digest)


if __name__ == '__main__':
    main()
