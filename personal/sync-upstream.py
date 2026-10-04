#!/usr/bin/env python3
"""Merge an official stable tag on a reviewable branch, leaving personal intact."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag', nargs='?')
    args = parser.parse_args()
    if run('git', 'status', '--porcelain'):
        raise SystemExit('Commit or stash your changes before merging upstream.')
    if run('git', 'branch', '--show-current') != 'personal':
        raise SystemExit('Start from the personal branch.')
    tag = args.tag or json.loads(run('gh', 'api', 'repos/pingdotgg/t3code/releases/latest'))['tag_name']
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise SystemExit('Choose an official stable vMAJOR.MINOR.PATCH tag.')
    metadata = json.loads((ROOT / 'personal/release.json').read_text())
    if metadata['upstreamTag'] == tag:
        print(f'Already based on {tag}.')
        return
    run('git', 'fetch', 'upstream', f'refs/tags/{tag}:refs/tags/{tag}')
    run('git', 'switch', '-c', f'update/{tag}', 'personal')
    try:
        subprocess.run(['git', 'merge', '--no-ff', '--no-edit', tag], cwd=ROOT, check=True)
    except subprocess.CalledProcessError:
        raise SystemExit('Merge conflicts remain on the update branch. Resolve them, or git merge --abort.')
    metadata |= {'upstreamTag': tag, 'revision': 1}
    (ROOT / 'personal/release.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Review the merge and run personal/check.sh, then commit the release metadata.')
    print('When checks pass: git switch personal && git merge --ff-only ' + f'update/{tag}')
    print('Push personal, then run the Personal Linux Release workflow.')


if __name__ == '__main__':
    main()
