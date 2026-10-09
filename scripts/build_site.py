#!/usr/bin/env python3
"""Build an offline single-file reader from course-schema.json + Markdown.
Python 3.10+, standard library only. Never fetches remote content.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import mimetypes
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

def slug(text: str) -> str:
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'[`*_~]', '', text).lower().strip()
    return re.sub(r'[^\w\-\s]', '', text, flags=re.UNICODE).replace(' ', '-') or 'section'

class Markdown:
    """Safe subset: headings, fences, lists, tables, quotes, links and emphasis.

    Raw HTML is escaped. Inline code is isolated before other formatting.
    Relative Markdown links are compiled to embedded document routes.
    """
    def __init__(self, root: Path, source: str, routes: dict[str, str]):
        self.root, self.source, self.routes = root, source, routes
        self.headings: list[dict[str, str | int]] = []
        self.ids: dict[str, int] = {}

    def local(self, target: str) -> tuple[str | None, str]:
        target = html.unescape(target.strip())
        parsed = urlsplit(target)
        if parsed.scheme:
            return (target, '') if parsed.scheme.lower() in ('https', 'http', 'mailto') else (None, '')
        if target.startswith('//') or '\\' in target:
            return None, ''
        if target.startswith('#'):
            return '#section/' + quote(self.routes.get(self.source, 'document/' + self.source), safe='/') + '/' + quote(unquote(target[1:]), safe=''), ''
        candidate = (self.root / self.source).parent / unquote(parsed.path)
        try:
            rel = candidate.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return None, ''
        if rel in self.routes:
            route = self.routes[rel]
            if parsed.fragment:
                return '#section/' + quote(route, safe='/') + '/' + quote(unquote(parsed.fragment), safe=''), rel
            return '#' + quote(route, safe='/'), rel
        return quote(rel, safe='/') + ('#' + quote(unquote(parsed.fragment), safe='') if parsed.fragment else ''), rel

    def inline(self, raw: str) -> str:
        tokens: list[str] = []
        def hold(value: str) -> str:
            tokens.append(value)
            return f'\x00{len(tokens)-1}\x00'
        # A control character cannot forge a protected token from source Markdown.
        raw = raw.replace('\x00', '')
        raw = re.sub(r'(`+)(.+?)\1', lambda m: hold('<code>' + html.escape(m[2]) + '</code>'), raw)
        def image(m: re.Match[str]) -> str:
            alt, target = m[1], m[2]
            href, rel = self.local(target)
            file = self.root / rel if rel else None
            if file and file.is_file() and file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg') and file.stat().st_size <= 2_000_000:
                # SVG can contain active scripts, so do not inline it as markup.
                data = base64.b64encode(file.read_bytes()).decode('ascii')
                mime = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
                return hold(f'<img src="data:{mime};base64,{data}" alt="{html.escape(alt, quote=True)}" loading="lazy">')
            if href and href.startswith(('https:', 'http:')):
                return hold(f'<a href="{html.escape(href, quote=True)}" rel="noopener noreferrer">{html.escape(alt or "Изображение")} (внешнее изображение)</a>')
            return hold('<span class="missing-image">' + html.escape(alt) + '</span>')
        raw = re.sub(r'!\[([^\]]*)\]\(([^\s)]+)(?:\s+"[^"]*")?\)', image, raw)
        def link(m: re.Match[str]) -> str:
            label, target = m[1], m[2]
            href, _ = self.local(target)
            if not href:
                return hold(html.escape(label))
            external = ' rel="noopener noreferrer"' if href.startswith(('http:', 'https:')) else ''
            return hold(f'<a href="{html.escape(href, quote=True)}"{external}>{html.escape(label)}</a>')
        raw = re.sub(r'\[((?:[^\[\]]|\[[^\[\]]*\])+)\]\(([^\s)]+)(?:\s+"[^"]*")?\)', link, raw)
        raw = re.sub(r'<(https?://[^\s>]+)>', lambda m: hold(f'<a href="{html.escape(m[1], quote=True)}" rel="noopener noreferrer">{html.escape(m[1])}</a>'), raw)
        raw = html.escape(raw)
        raw = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', raw)
        raw = re.sub(r'__(.+?)__', r'<strong>\1</strong>', raw)
        raw = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', raw)
        raw = re.sub(r'~~(.+?)~~', r'<s>\1</s>', raw)
        for _ in range(8):
            if '\x00' not in raw: break
            raw = re.sub(r'\x00(\d+)\x00', lambda m: tokens[int(m[1])], raw)
        return raw

    @staticmethod
    def table_cells(line: str) -> list[str]:
        line = line.strip().strip('|')
        return [part.strip().replace('\\|', '|') for part in re.split(r'(?<!\\)\|', line)]

    def render(self, text: str) -> str:
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        return self.blocks(lines)

    def blocks(self, lines: list[str]) -> str:
        out: list[str] = []
        i = 0
        list_re = re.compile(r'^(\s*)([-+*]|\d+[.)])\s+(.+)$')
        def starts(line: str) -> bool:
            return bool(re.match(r'^\s*(?:#{1,6}\s|```|~~~|>\s?|(?:[-+*]|\d+[.)])\s|(?:---+|\*\*\*+|___+)\s*$)', line))
        while i < len(lines):
            line = lines[i]
            if not line.strip(): i += 1; continue
            fence = re.match(r'^\s*(`{3,}|~{3,})(.*)$', line)
            if fence:
                marker, language = fence[1], fence[2].strip().split(' ')[0]
                code: list[str] = []; i += 1
                while i < len(lines) and not re.match(r'^\s*' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*$', lines[i]):
                    code.append(lines[i]); i += 1
                i += 1
                lang = re.sub(r'[^\w+-]', '', language) or 'text'
                out.append('<div class="code-block"><div class="code-top"><span>' + html.escape(lang) + '</span><button type="button" class="copy-code" aria-label="Скопировать блок кода">Копировать</button></div><pre tabindex="0"><code class="language-' + html.escape(lang, quote=True) + '">' + html.escape('\n'.join(code)) + '</code></pre></div>')
                continue
            if line.strip() == '<details>':
                j = i + 1
                while j < len(lines) and not lines[j].strip(): j += 1
                summary = re.fullmatch(r'\s*<summary>([^<>]+)</summary>\s*', lines[j]) if j < len(lines) else None
                if summary:
                    j += 1; start = j; depth = 1; active_fence = None
                    while j < len(lines):
                        strip = lines[j].strip()
                        found_fence = re.match(r'^(`{3,}|~{3,})', strip)
                        if found_fence:
                            if active_fence is None: active_fence = found_fence[1][0]
                            elif strip.startswith(active_fence * 3): active_fence = None
                        elif active_fence is None:
                            if strip == '<details>': depth += 1
                            elif strip == '</details>':
                                depth -= 1
                                if depth == 0: break
                        j += 1
                    if depth != 0: raise ValueError('Unclosed safe details block in ' + self.source)
                    out.append('<details class="lesson-hint"><summary>' + self.inline(summary[1]) + '</summary><div>' + self.blocks(lines[start:j]) + '</div></details>')
                    i = j + 1; continue
            anchor = re.fullmatch(r'''\s*<a id=["']([a-zA-Z0-9_-]+)["']></a>\s*''', line)
            if anchor:
                ident = anchor[1]
                if ident in self.ids: raise ValueError('Duplicated explicit anchor: ' + ident + ' in ' + self.source)
                self.ids[ident] = 1
                out.append('<span class="anchor-target" id="article-' + ident + '" aria-hidden="true"></span>'); i += 1; continue
            heading = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
            if heading:
                level = len(heading[1]); title = heading[2]; base = slug(title)
                count = self.ids.get(base, 0); self.ids[base] = count + 1
                ident = base + (f'-{count}' if count else '')
                self.headings.append({'id': ident, 'title': re.sub(r'[`*_]', '', title), 'level': level})
                # Site owns its h1; document titles begin at h2.
                actual = min(6, level + 1)
                out.append(f'<h{actual} id="article-{html.escape(ident, quote=True)}">{self.inline(title)}</h{actual}>'); i += 1; continue
            if re.match(r'^\s*(---+|\*\*\*+|___+)\s*$', line): out.append('<hr>'); i += 1; continue
            if line.lstrip().startswith('>'):
                quote_lines = []
                while i < len(lines) and (lines[i].lstrip().startswith('>') or not lines[i].strip()):
                    quote_lines.append(re.sub(r'^\s*> ?', '', lines[i])); i += 1
                out.append('<blockquote>' + self.blocks(quote_lines) + '</blockquote>'); continue
            if i + 1 < len(lines) and '|' in line and re.match(r'^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$', lines[i+1]):
                cells = self.table_cells(line); i += 2
                rows = []
                while i < len(lines) and '|' in lines[i] and lines[i].strip():
                    vals = self.table_cells(lines[i]); vals += [''] * max(0, len(cells)-len(vals))
                    rows.append('<tr>' + ''.join('<td>' + self.inline(v) + '</td>' for v in vals[:len(cells)]) + '</tr>'); i += 1
                out.append('<div class="table-scroll" role="region" aria-label="Таблица, прокручивается по горизонтали" tabindex="0"><table><thead><tr>' + ''.join('<th scope="col">' + self.inline(c) + '</th>' for c in cells) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'); continue
            match = list_re.match(line)
            if match:
                base_indent = len(match[1]); ordered = match[2][0].isdigit(); tag = 'ol' if ordered else 'ul'; items = []
                start_num = int(re.match(r'\d+', match[2])[0]) if ordered else 1
                while i < len(lines):
                    current = list_re.match(lines[i])
                    if not current or len(current[1]) != base_indent or current[2][0].isdigit() != ordered: break
                    chunk = [current[3]]; indent_content = len(current[1])+len(current[2])+1; i += 1
                    while i < len(lines):
                        nxt = list_re.match(lines[i]); leading = len(lines[i])-len(lines[i].lstrip())
                        if nxt and len(nxt[1]) <= base_indent: break
                        if lines[i].strip() and leading <= base_indent: break
                        if not lines[i].strip():
                            if i+1 >= len(lines) or (lines[i+1].strip() and len(lines[i+1])-len(lines[i+1].lstrip()) <= base_indent): break
                        chunk.append(lines[i][min(indent_content, leading):]); i += 1
                    task = re.match(r'^\[([ xX])\]\s+(.*)$', chunk[0])
                    if task:
                        chunk[0] = task[2]
                        mark = '☑' if task[1].lower() == 'x' else '☐'
                        items.append('<li class="source-task"><span aria-label="' + ('Отмечено' if task[1].lower() == 'x' else 'Не отмечено') + '">' + mark + '</span><div>' + self.blocks(chunk) + '</div></li>')
                    else: items.append('<li>' + self.blocks(chunk) + '</li>')
                    if i < len(lines) and not lines[i].strip():
                        j = i
                        while j < len(lines) and not lines[j].strip(): j += 1
                        nxt = list_re.match(lines[j]) if j < len(lines) else None
                        if nxt and len(nxt[1]) == base_indent and nxt[2][0].isdigit() == ordered: i = j
                        else: break
                attr = f' start="{start_num}"' if ordered and start_num != 1 else ''
                out.append(f'<{tag}{attr}>' + ''.join(items) + f'</{tag}>'); continue
            paragraph = [line.strip()]; i += 1
            while i < len(lines) and lines[i].strip() and not starts(lines[i]):
                if i+1 < len(lines) and '|' in lines[i] and re.match(r'^\s*\|?\s*:?-{3,}', lines[i+1]): break
                paragraph.append(lines[i].strip()); i += 1
            out.append('<p>' + self.inline(' '.join(paragraph)) + '</p>')
        return '\n'.join(out)

def normalize(schema: dict) -> dict:
    if schema.get('schema_version') != 1: raise ValueError('Expected schema_version: 1')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', schema.get('id', '')): raise ValueError('Invalid course id')
    ids = set()
    for module in schema['modules']:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', module['id']) or module['id'] in ids: raise ValueError('Invalid or duplicated module id')
        ids.add(module['id'])
        if module.get('track') not in ('core', 'optional'): raise ValueError('Invalid track')
        points = module.get('checkpoints', [])
        if not points or any(not isinstance(c, dict) or not c.get('label') or not re.fullmatch(r'[a-zA-Z0-9_-]+', c.get('id','')) for c in points): raise ValueError('Every module needs named checkpoints')
        if len({c['id'] for c in points}) != len(points): raise ValueError('Duplicated checkpoint')
    for module in schema['modules']:
        if not set(module.get('prerequisites', [])).issubset(ids): raise ValueError('Unknown prerequisite')
    if schema.get('review_offsets_days', [1,3,7,21]) != [1,3,7,21]: raise ValueError('Update review model and tests if review offsets change')
    return schema

def build(root: Path, schema_path: Path, output: Path, allow_missing: bool = False) -> dict:
    schema = normalize(json.loads(schema_path.read_text(encoding='utf-8')))
    routes = {m['path']: 'module/' + m['id'] for m in schema['modules']}
    markdown_paths = sorted({str(p.relative_to(root).as_posix()) for p in (root/'docs').rglob('*.md')} | {d['path'] for d in schema.get('documents', [])})
    if (root/'README.md').exists(): markdown_paths.append('README.md')
    for path in markdown_paths:
        if path not in routes: routes[path] = 'document/' + path
    payload = {**schema, 'documents': [], 'build': ''}
    source_hash = hashlib.sha256(schema_path.read_bytes())
    missing = []
    def document(path: str, title: str | None = None) -> dict:
        candidate = (root/path).resolve()
        try: candidate.relative_to(root.resolve())
        except ValueError: raise ValueError('Source is outside repository: ' + path)
        if not candidate.is_file():
            if not allow_missing: raise FileNotFoundError('Missing required Markdown: ' + path)
            missing.append(path)
            content = '# Материал ожидает интеграции\n\nЭто временная тестовая сборка интерфейса. Файл ' + path + ' ещё не добавлен.'
        else: content = candidate.read_text(encoding='utf-8')
        source_hash.update(path.encode()); source_hash.update(content.encode())
        renderer = Markdown(root, path, routes)
        rendered = renderer.render(content)
        h1 = next((h['title'] for h in renderer.headings if h['level']==1), None)
        return {'path':path, 'title':title or h1 or Path(path).stem, 'html':rendered, 'headings':renderer.headings, 'searchText':re.sub(r'\s+', ' ', content).lower()}
    for m in payload['modules']: m.update(document(m['path'],m['title']))
    preferred = {d['path']: d['title'] for d in schema.get('documents', [])}
    priority = ['docs/START_HERE.md','docs/SAFETY.md','docs/TOOLCHAIN.md','docs/DEBUGGING.md','docs/SOURCES.md','docs/ROADMAP.md','docs/ASSESSMENT.md','docs/CAPSTONE.md','docs/AI_WORKFLOW.md','docs/progress-template.md']
    docs = [p for p in markdown_paths if p not in {m['path'] for m in schema['modules']}]
    docs.sort(key=lambda p: (priority.index(p) if p in priority else len(priority), p))
    payload['documents'] = [document(p,preferred.get(p)) for p in docs]
    assets = {name: (ROOT/'site'/name).read_text(encoding='utf-8') for name in ('index.template.html','styles.css','state.js','app.js')}
    for value in assets.values(): source_hash.update(value.encode())
    payload['build'] = source_hash.hexdigest()[:12]
    data = json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    result = assets['index.template.html'].replace('/* SITE_CSS */',assets['styles.css']).replace('/* SITE_STATE */',assets['state.js']).replace('/* SITE_APP */',assets['app.js']).replace('COURSE_DATA_JSON',data)
    if 'COURSE_DATA_JSON' in result: raise ValueError('Unreplaced template token')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(result,encoding='utf-8')
    report={'output':str(output),'modules':len(payload['modules']),'documents':len(payload['documents']),'bytes':output.stat().st_size,'build':payload['build'],'missing':missing}
    return report

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT,help='Repository root containing docs/')
    parser.add_argument('--schema',type=Path,help='Default: ROOT/course-schema.json')
    parser.add_argument('--output',type=Path,help='Default: ROOT/index.html')
    parser.add_argument('--allow-missing',action='store_true',help='Temporary shell QA only; never publish this build')
    args=parser.parse_args()
    try: print(json.dumps(build(args.root.resolve(),(args.schema or args.root/'course-schema.json').resolve(),(args.output or args.root/'index.html').resolve(),args.allow_missing),ensure_ascii=False,indent=2))
    except (ValueError,KeyError,OSError) as error: print('Build failed: '+str(error),file=sys.stderr); sys.exit(1)
