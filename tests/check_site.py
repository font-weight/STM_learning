#!/usr/bin/env python3
"""Static release checks. This is NOT a browser or a hardware test."""
from __future__ import annotations
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

class Inspect(HTMLParser):
    def __init__(self): super().__init__();self.links=[];self.ids=[];self.remote_assets=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='a' and 'href' in attrs:self.links.append(attrs['href'])
        if tag in ('script','img','iframe','audio','video','source','link'):
            url=attrs.get('src') or attrs.get('href') or ''
            if url and not url.startswith(('data:','#')):self.remote_assets.append((tag,url))

def check(root:Path,allow_missing:bool=False):
    source=(root/'index.html').read_text(encoding='utf-8')
    match=re.search(r'<script id="course-data" type="application/json">(.*?)</script>',source,re.S)
    if not match:raise ValueError('Embedded course JSON missing')
    data=json.loads(match[1]);errors=[];warnings=[]
    if len(data['modules'])!=14:errors.append('Expected 14 modules')
    if len({m['id'] for m in data['modules']})!=len(data['modules']):errors.append('Duplicate module ids')
    if sum(m.get('hours',0) for m in data['modules'] if m['track']=='core')!=data.get('core_hours'):errors.append('Core hours differ from module sum')
    docs={'module/'+m['id']:m for m in data['modules']}
    docs.update({'document/'+d['path']:d for d in data['documents']})
    parsed={}
    for route,d in docs.items():
        parser=Inspect();parser.feed(d['html']);parsed[route]=parser
        if len(parser.ids)!=len(set(parser.ids)):errors.append(route+': duplicate element IDs')
        if parser.remote_assets:errors.append(route+': content depends on nonembedded assets')
        if 'Материал ожидает интеграции' in d['html']:errors.append(route+': missing-source placeholder')
    checked=0
    for route,p in parsed.items():
        for href in p.links:
            checked+=1
            if href.startswith('#section/'):
                parts=unquote(href[9:]).split('/');anchor='article-'+parts.pop();dest='/'.join(parts)
                if dest not in parsed:errors.append(route+': unknown anchor destination '+href)
                elif anchor not in parsed[dest].ids:errors.append(route+': missing anchor '+href)
            elif href.startswith(('#module/','#document/')):
                if unquote(href[1:]) not in docs:errors.append(route+': unknown route '+href)
            elif urlsplit(href).scheme in ('http','https','mailto'):continue
            elif href.startswith('#'):continue
            else:
                file=(root/unquote(urlsplit(href).path)).resolve()
                try:file.relative_to(root.resolve())
                except ValueError:errors.append(route+': path escapes repo '+href);continue
                if not file.exists():
                    (warnings if allow_missing else errors).append(route+': missing local asset '+href)
    shell=Inspect();shell.feed(source[:match.start()])
    if shell.remote_assets:errors.append('Shell has external runtime assets: '+str(shell.remote_assets))
    if re.search(r'\bfetch\s*\(|XMLHttpRequest|https?://[^\s]+\.css',source[match.end():]):errors.append('Runtime network dependency detected')
    report={'kind':'static-release-check','modules':len(data['modules']),'documents':len(data['documents']),'internal_and_external_links_checked':checked,'build':data['build'],'errors':errors,'warnings':warnings}
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--allow-missing-assets',action='store_true');args=parser.parse_args()
    try:report=check(args.root,args.allow_missing_assets)
    except (ValueError,OSError,KeyError) as error:report={'kind':'static-release-check','errors':[str(error)]}
    print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(bool(report['errors']))
