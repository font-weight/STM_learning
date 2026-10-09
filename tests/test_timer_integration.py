#!/usr/bin/env python3
"""Optional companion integration contracts, without a real browser or hardware."""
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
TIMER = ROOT / 'practice/timer/index.html'


class Inspect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.assets, self.ids, self.navs, self.scripts = [], [], [], [], []
        self.forms, self.metas = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs)
        if tag in ('link', 'img', 'iframe', 'audio', 'video', 'source', 'script'):
            url = attrs.get('src') or attrs.get('href')
            if url:
                self.assets.append(url)
        if tag == 'nav':
            self.navs.append(attrs)
        if tag == 'script':
            self.scripts.append(attrs)
        if tag == 'form':
            self.forms.append(attrs)
        if tag == 'meta':
            self.metas.append(attrs)


def inspect(source):
    parser = Inspect()
    parser.feed(source)
    return parser


class TimerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TIMER.read_text(encoding='utf-8')
        cls.parser = inspect(cls.html)
        cls.scripts = dict(re.findall(r'<script id="([^"]+)">([\s\S]*?)</script>', cls.html))
        source = (ROOT / 'index.html').read_text(encoding='utf-8')
        match = re.search(r'<script id="course-data" type="application/json">(.*?)</script>', source, re.S)
        if not match:
            raise ValueError('Build the course first: embedded course JSON missing')
        cls.course = json.loads(match[1])
        cls.docs = {'module/' + d['id']: d for d in cls.course['modules']}
        cls.docs.update({'document/' + d['path']: d for d in cls.course['documents']})

    def test_reviewed_calculation_and_handlers_are_byte_identical(self):
        expected = {
            'timer-core': 'eac2e8897be33952d10c2b54ad5a65ed75a3a5cb9c7005756283eb0c4f1d23f1',
            'timer-ui': '4d459aebce8f3a5bc7b895bc82e6695e9dcffaf2ace8db9032221d259c50dd61',
        }
        self.assertEqual(set(self.scripts), set(expected))
        for name, digest in expected.items():
            self.assertEqual(sha256(self.scripts[name].encode()).hexdigest(), digest, name)

    def test_no_runtime_assets_network_or_progress_storage(self):
        self.assertEqual(self.parser.assets, [])
        self.assertEqual(len(self.parser.scripts), 2)
        self.assertEqual(len(self.parser.forms), 1)
        self.assertNotIn('action', self.parser.forms[0])
        scripts = '\n'.join(self.scripts.values())
        self.assertNotRegex(scripts, r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|localStorage|sessionStorage|indexedDB|serviceWorker|CourseState|postMessage|cookie|opener)\b')
        self.assertNotRegex(scripts, r'(?:location|history)\s*[.\[]')
        policy = next(m['content'] for m in self.parser.metas if m.get('http-equiv') == 'Content-Security-Policy')
        for part in ["default-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'"]:
            self.assertIn(part, policy)

    def test_relevant_markdown_links_resolve_to_companion(self):
        for rel in ['docs/TOOLCHAIN.md', 'docs/labs/05-pwm.md']:
            source = (ROOT / rel).read_text(encoding='utf-8')
            links = re.findall(r'\[[^\]]+\]\(([^\s)]+)\)', source)
            matches = [href for href in links if 'practice/timer/index.html' in href]
            self.assertEqual(len(matches), 1, rel)
            self.assertEqual(((ROOT / rel).parent / matches[0]).resolve(), TIMER.resolve())
            self.assertIn('Необязательно', source)
            self.assertIn('можно пропустить', source.lower())
            self.assertIn('«по памяти»', source.lower())

    def test_built_reader_has_two_discoverable_same_tab_file_links(self):
        for route in ['module/L05', 'document/docs/TOOLCHAIN.md']:
            links = inspect(self.docs[route]['html']).links
            matches = [a for a in links if a.get('href') == 'practice/timer/index.html']
            self.assertEqual(len(matches), 1, route)
            self.assertNotIn('target', matches[0])
            self.assertTrue((ROOT / matches[0]['href']).is_file())

    def test_all_local_return_links_resolve_to_real_reader_routes_and_anchor(self):
        returns = []
        for link in self.parser.links:
            parsed = urlsplit(link['href'])
            if parsed.scheme:
                continue
            self.assertNotIn('target', link)
            self.assertNotIn('onclick', link)
            self.assertEqual((TIMER.parent / unquote(parsed.path)).resolve(), (ROOT / 'index.html').resolve())
            fragment = unquote(parsed.fragment)
            if fragment.startswith('section/'):
                route, anchor = fragment[len('section/'):].rsplit('/', 1)
                self.assertIn(route, self.docs)
                self.assertIn('article-' + anchor, inspect(self.docs[route]['html']).ids)
            else:
                self.assertIn(fragment, self.docs)
            returns.append(fragment)
        self.assertEqual(returns.count('module/L05'), 2)
        self.assertEqual(returns.count('section/document/docs/TOOLCHAIN.md/clocks'), 1)
        self.assertEqual([n.get('aria-label') for n in self.parser.navs], ['Возврат к курсу'])
        self.assertEqual(len(self.parser.ids), len(set(self.parser.ids)))

    def test_only_external_link_is_user_activated_official_source(self):
        external = [a for a in self.parser.links if urlsplit(a['href']).scheme]
        self.assertEqual(len(external), 1)
        self.assertEqual(urlsplit(external[0]['href']).hostname, 'www.st.com')
        self.assertEqual(urlsplit(external[0]['href']).scheme, 'https')
        self.assertTrue(external[0]['href'].endswith('.pdf'))
        self.assertIn('noopener', external[0]['rel'].split())
        self.assertIn('noreferrer', external[0]['rel'].split())
        for text in ['Rev 21', '§7.2', '14.4.11–14.4.13', '15.4.11–15.4.12']:
            self.assertIn(text, self.html)

    def test_addition_is_optional_with_unchanged_course_scope(self):
        self.assertEqual(self.course['schema_version'], 1)
        self.assertEqual(self.course['id'], 'stm32f103-practical-ru')
        self.assertEqual(self.course['core_hours'], 48)
        self.assertEqual([m['id'] for m in self.course['modules']], [f'L{i:02}' for i in range(14)])
        schema = (ROOT / 'course-schema.json').read_text(encoding='utf-8')
        self.assertNotIn('practice/timer', schema)
        self.assertNotIn('practice/timer', (ROOT / 'site/app.js').read_text(encoding='utf-8'))
        for text in ['можно пропустить', 'не добавляет обязательных часов, оборудования', 'не отмечает лабораторные как пройденные', 'Для задания «по памяти» закройте помощник']:
            self.assertIn(text, self.html)

    def test_prediction_gate_bounds_and_review_fixes_remain_visible_in_source(self):
        self.assertRegex(self.html, r'<section id="result"[^>]* hidden>')
        for text in ['PSC/ARR уже применены', 'CEN=1, UDIS=0', 'RCR=0', '0…65535', 'ARR=0', '1 ≤ CCR ≤ ARR', 'Center-aligned, one-pulse, slave/reset/gated modes', 'не доказывает конфигурацию платы', 'f_PWM · частота повторения edge-aligned PWM']:
            self.assertIn(text, self.html)
        self.assertIn('.metric dd p{font-size:14px;font-weight:400;line-height:1.6}', self.html)
        self.assertIn('.course-nav{display:flex;flex-wrap:wrap;', self.html)
        self.assertIn('min-height:44px', self.html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
