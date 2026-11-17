"""Install pinned Windows/Python 3.11 wheels without the PyPI Simple index."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / '.cache/action-encoder/wheels'
LOCK = pathlib.Path(__file__).with_name('requirements.lock.txt')
PINS = {
    'filelock': '3.20.0', 'typing_extensions': '4.15.0', 'sympy': '1.14.0',
    'networkx': '3.5', 'jinja2': '3.1.6', 'fsspec': '2025.10.0',
    'mpmath': '1.3.0', 'markupsafe': '3.0.3', 'transformers': '4.57.6',
    'huggingface-hub': '0.36.0', 'numpy': '2.3.5', 'packaging': '25.0',
    'pyyaml': '6.0.3', 'regex': '2025.11.3', 'requests': '2.32.5',
    'tokenizers': '0.22.1', 'safetensors': '0.6.2', 'tqdm': '4.67.1',
    'hf-xet': '1.2.0', 'colorama': '0.4.6', 'certifi': '2025.11.12',
    'charset-normalizer': '3.4.4', 'idna': '3.11', 'urllib3': '2.6.3',
}


def read_url(url: str) -> bytes:
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=20) as response:
        chunks = []
        while chunk := response.read(1024 * 256):
            chunks.append(chunk)
            if time.monotonic() - started > 60:
                raise TimeoutError('Download exceeded 60 seconds')
        return b''.join(chunks)


def sha256(path: pathlib.Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch_wheel(entry: dict) -> pathlib.Path:
    path = CACHE / entry['filename']
    if path.exists() and sha256(path) == entry['sha256']:
        print('Cached ' + entry['name'], flush=True)
        return path
    for attempt in range(2):
        try:
            source_url = entry['url'] if attempt == 0 else entry['url'].replace(
                'https://files.pythonhosted.org/packages/',
                'https://pypi.tuna.tsinghua.edu.cn/packages/')
            data = read_url(source_url)
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Wheel SHA256 mismatch: ' + entry['name'])
            temp = path.with_suffix('.part')
            temp.write_bytes(data)
            temp.replace(path)
            path.with_suffix('.source.json').write_text(json.dumps(
                {'url': source_url, 'sha256': entry['sha256']}, indent=2), encoding='utf-8')
            print('Downloaded ' + entry['name'], flush=True)
            return path
        except Exception as exc:
            print(f'Download retry {entry["name"]}: {type(exc).__name__}', flush=True)
            if attempt == 1:
                raise
    raise AssertionError('unreachable')


def resolve(name: str, version: str) -> dict:
    # pip's bundled packaging is available before installing any third-party dependencies.
    from pip._vendor.packaging.tags import sys_tags
    from pip._vendor.packaging.utils import parse_wheel_filename
    tags = set(sys_tags())
    metadata_path = CACHE / f'{name}-{version}.json'
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    else:
        print('Resolving ' + name, flush=True)
        for attempt in range(2):
            try:
                metadata_bytes = read_url(f'https://pypi.org/pypi/{name}/{version}/json')
                metadata = json.loads(metadata_bytes)
                metadata_path.write_bytes(metadata_bytes)
                break
            except Exception as exc:
                print(f'Metadata retry {name}: {type(exc).__name__}', flush=True)
                if attempt == 1:
                    raise RuntimeError('Cannot fetch pinned metadata: ' + name) from exc
    for item in metadata['urls']:
        if item['packagetype'] != 'bdist_wheel' or item.get('yanked'):
            continue
        if parse_wheel_filename(item['filename'])[3] & tags:
            return {'name': name, 'version': version, 'filename': item['filename'],
                    'url': item['url'], 'sha256': item['digests']['sha256']}
    raise RuntimeError('No compatible wheel: ' + name)


def main() -> None:
    if sys.version_info[:2] != (3, 11) or sys.platform != 'win32':
        raise SystemExit('This lock targets Python 3.11 on Windows x64.')
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest_path = pathlib.Path(__file__).with_name('wheels.lock.json')
    if manifest_path.exists():
        entries = json.loads(manifest_path.read_text(encoding='utf-8'))['wheels']
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            entries = list(pool.map(lambda pair: resolve(*pair), PINS.items()))
        manifest_path.write_text(json.dumps({'platform': 'win_amd64', 'python': '3.11',
                                          'wheels': entries}, indent=2) + '\n', encoding='utf-8')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        paths = list(pool.map(fetch_wheel, entries))
    # Torch is installed separately from its official CPU distribution index.
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--no-index', '--no-deps', *map(str, paths)], check=True)
    LOCK.write_text('# Windows x64 / Python 3.11; wheel hashes are in wheels.lock.json.\n'
                    'torch==2.9.1+cpu\n' + ''.join(
                        f"{entry['name']}=={entry['version']}\n"
                        for entry in sorted(entries, key=lambda x: x['name'])), encoding='utf-8')


if __name__ == '__main__':
    main()
