"""Check project Markdown with the installed skill's bundled structural rules."""
from fantasy_agent.paths import ROOT as PROJECT_ROOT
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = PROJECT_ROOT


def documents():
    return sorted([*ROOT.glob('*.md'), *ROOT.joinpath('docs').rglob('*.md'),
                   *ROOT.joinpath('tests').rglob('*.md')])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    spec = importlib.util.spec_from_file_location('ste_lint', ROOT / 'tools/ste/scripts/ste-lint.py')
    linter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(linter)
    findings = []
    words = 0
    for path in args.files or documents():
        path = path.resolve()
        if path.is_relative_to(ROOT / 'data'):
            parser.error('Files under data/ are excluded by user instruction')
        current, count = linter.lint(path.read_text(), filename=str(path.relative_to(ROOT)))
        # Lexical rules are advisory in the skill's prose mode. The checker
        # cannot distinguish our technical operations from interchangeable verbs.
        for item in current:
            if item['rule'] == 'synonym-rotation':
                item['level'] = 'advisory'
        findings.extend(current)
        words += count
    hard = sum(item['level'] == 'advisory-free' for item in findings)
    if args.json:
        print(json.dumps({'hard_findings': hard, 'words': words, 'findings': findings}, indent=2))
    else:
        for item in findings:
            if item['level'] == 'advisory-free':
                print(f"{item['file']}:{item['line']}: {item['rule']}: {item['message']}")
        print(f'{hard} structural findings; {len(findings)-hard} advisory findings; {words} words.')
        print('Review meaning, instruction length, vocabulary and advisory findings manually.')
    return int(hard > 0)


if __name__ == '__main__':
    raise SystemExit(main())
