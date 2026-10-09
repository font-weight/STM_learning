#!/usr/bin/env python3
"""Validate course structure and local Markdown targets; does not test a board."""
from pathlib import Path
import json
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
errors = []
def check(condition, message):
    if not condition:
        errors.append(message)
def without_fences(text):
    return re.sub(r'^```[^\n]*\n.*?^```\s*$', '', text, flags=re.M | re.S)
def anchors(text):
    found = set(re.findall(r'<a\s+id="([\w-]+)"\s*></a>', text))
    seen = {}
    for line in without_fences(text).splitlines():
        if re.match(r'^#{1,6}\s+', line):
            title = re.sub(r'^#{1,6}\s+', '', line).strip().rstrip('#').strip()
            title = re.sub(r'[`*_~]', '', title)
            slug = re.sub(r'[^\w\s-]', '', title.lower(), flags=re.UNICODE).replace(' ', '-')
            n = seen.get(slug, 0)
            seen[slug] = n + 1
            found.add(slug if n == 0 else f'{slug}-{n}')
    return found
try:
    course = json.loads((ROOT / 'course-schema.json').read_text(encoding='utf-8'))
except (OSError, ValueError) as exc:
    sys.exit(f'FAIL: course-schema.json: {exc}')
modules = course.get('modules', [])
check(bool(modules), 'No modules')
ids = [m.get('id') for m in modules]
check(len(ids) == len(set(ids)), 'Duplicate module IDs')
paths = [m.get('path') for m in modules]
check(len(paths) == len(set(paths)), 'Duplicate module paths')
for index, module in enumerate(modules):
    mid = module.get('id', '?')
    path = module.get('path', '')
    check(bool(path) and (ROOT / path).is_file(), f'{mid}: missing Markdown {path}')
    prerequisites = module.get('prerequisites', module.get('prereqs', []))
    for pre in prerequisites:
        check(pre in ids[:index], f'{mid}: prerequisite {pre} missing or not earlier')
    checks = module.get('checkpoints', [])
    check(bool(checks), f'{mid}: missing evidence checkpoints')
    cids = [c.get('id') for c in checks]
    check(len(cids) == len(set(cids)), f'{mid}: duplicate checkpoint IDs')
    check(bool(module.get('gate')), f'{mid}: missing skill gate')

link_count = 0
for file in sorted(ROOT.rglob('*.md')):
    if any(part in {'.git', 'node_modules', 'build', '.build'} for part in file.parts):
        continue
    text = file.read_text(encoding='utf-8')
    check(sum(line.startswith('```') for line in text.splitlines()) % 2 == 0,
          f'{file.relative_to(ROOT)}: unbalanced triple-backtick fences')
    for href in re.findall(r'\[[^\]\n]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', without_fences(text)):
        href = href.strip('<>')
        parts = urlsplit(href)
        if parts.scheme or parts.netloc:
            continue
        target = (file.parent / unquote(parts.path)).resolve() if parts.path else file.resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            errors.append(f'{file.relative_to(ROOT)}: link escapes repository: {href}')
            continue
        link_count += 1
        check(target.exists(), f'{file.relative_to(ROOT)}: missing local target {href}')
        if target.is_file() and target.suffix == '.md' and parts.fragment:
            check(unquote(parts.fragment) in anchors(target.read_text(encoding='utf-8')),
                  f'{file.relative_to(ROOT)}: missing anchor {href}')

if errors:
    print('\n'.join('FAIL: ' + error for error in errors))
    sys.exit(1)
print(f'PASS: {len(modules)} modules, prerequisites, skill gates, local targets/anchors ({link_count} links).')
print('Scope: source structure only; not firmware compilation, device execution or learning assessment.')
