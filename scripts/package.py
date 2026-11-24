"""Package portable source and synthetic evidence; omit local private/runtime data."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'node_modules', '.next', 'out', '.venv', '.data', '.git', 'work', '__pycache__', '.pytest_cache', 'test-results', 'playwright-report'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with ZipFile(destination, 'w', ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDED for part in relative.parts):
                continue
            if not path.is_file() or path.resolve() == destination:
                continue
            if (path.name.startswith('.env') and path.name != '.env.example') or path.name in {'.DS_Store', '.npmrc'} or path.suffix in {'.pyc', '.pyo', '.blend1', '.tsbuildinfo'}:
                continue
            if path.suffix == '.log' and 'evidence' not in relative.parts:
                continue
            bundle.write(path, Path('keepsake3d') / relative)
            count += 1
    with ZipFile(destination) as bundle:
        assert bundle.testzip() is None
        assert not any('/.data/' in n or '/node_modules/' in n or n.endswith('/.env') for n in bundle.namelist())
    print(f'Created {destination.name}: {count} files, {destination.stat().st_size:,} bytes; archive integrity passed.')

if __name__ == '__main__':
    main()
