"""Run offline acceptance and record which source version passed."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from automation_store import utc
from storage import save_new


def source_digest(root):
    root = Path(root)
    digest = hashlib.sha256()
    paths = [*root.glob('*.py'), *root.joinpath('tests').rglob('*.py'), *root.joinpath('schemas').rglob('*.json')]
    paths += [p for p in root.joinpath('templates').rglob('*') if p.is_file()]
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run(root, output):
    root, output = Path(root), Path(output)
    before = source_digest(root)
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-v'], cwd=root,
                            capture_output=True, text=True, timeout=180)
    import re
    count = re.search(r'Ran (\d+) tests?', result.stderr)
    unchanged = before == source_digest(root)
    record = {'schema_version': 1, 'basis': 'verified_failure_exercises',
              'command': 'python3 -m unittest discover -v', 'recorded_at': utc(time.time()),
              'source_digest': before, 'passed': int(count[1]) if count and result.returncode == 0 and unchanged else 0,
              'failed': 0 if result.returncode == 0 and unchanged else 1,
              'source_unchanged': unchanged, 'live_acceptance': False}
    save_new(output, record)
    output.with_suffix('.log').write_text(result.stdout + result.stderr)
    return record


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    result = run(Path(__file__).resolve().parent, a.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['failed']))
