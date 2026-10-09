#!/usr/bin/env python3
"""Optional real-browser QA, separate from dependency-free course runtime.
Requires Python Playwright and a permitted Chromium installation. Does not publish.
Runs against file:// by default; pass --url for a permitted HTTP preview.
"""
from __future__ import annotations
import argparse
import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]

def run(url:str,output:Path,binary:str):
    output.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[];requests=[]
    def passed(name):checks.append(name)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=binary,headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,color_scheme='light',locale='ru-RU')
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda request:requests.append({'url':request.url,'type':request.resource_type}))
        page.goto(url,wait_until='load');expect(page.locator('.module-card')).to_have_count(14)
        page.screenshot(path=str(output/'desktop-home.png'),full_page=True)
        build=page.locator('#build-id').text_content().strip(' ·')
        passed('Home renders 14 modules')
        # Reading after the initial load must not require the network.
        context.set_offline(True)
        page.get_by_placeholder('Найти тему: UART, DMA, таймер…').fill('UART')
        count=page.locator('.module-card').count();assert 0<count<14
        page.get_by_placeholder('Найти тему: UART, DMA, таймер…').fill('')
        page.locator('[name=module-filter][value=optional]').check()
        assert page.locator('.module-card').count()==3
        page.locator('[name=module-filter][value=core]').check();expect(page.locator('.module-card')).to_have_count(14)
        page.locator('[name=module-filter][value=all]').check();passed('Search and core/extension filters work offline')
        page.locator('.module-card h3 a').first.click();expect(page.locator('h1')).to_contain_text('Плата')
        # Follow an internal document link and use browser history.
        source_link=page.locator('.article-body a[href^="#document/"]').first
        if source_link.count():
            source_link.click();assert '#document/' in page.url
            page.go_back();assert '#module/L00' in page.url
        page.locator('a[href="#module/L00"]').first.click();passed('Module routes, document links, repeated navigation and Back')
        # Mode changes are ordinary hash routes and must never award completion.
        before_recall=page.evaluate("localStorage.getItem('stm32-practice:stm32f103-practical-ru:v1')")
        page.locator('.lesson-actions a[href^="#recall/"]').click()
        expect(page.locator('#recall-panel')).to_be_visible();expect(page.locator('.lesson-layout')).not_to_be_visible()
        expect(page.locator('.learning-check')).not_to_be_visible()
        expect(page.locator('#recall-title')).to_be_focused()
        assert page.evaluate("localStorage.getItem('stm32-practice:stm32f103-practical-ru:v1')")==before_recall
        page.go_back();expect(page.locator('.lesson-layout')).to_be_visible()
        page.locator('.lesson-actions a[href^="#recall/"]').click()
        page.get_by_role('link',name='Сверить с материалом').click()
        expect(page.locator('#recall-panel')).not_to_be_visible()
        passed('Recall hides material, returns through history and comparison, and never changes progress')
        for checkbox in page.locator('[data-checkpoint]').all():checkbox.check()
        expect(page.locator('#sidebar-count')).to_have_text('1 / 14')
        expect(page.locator('#mark-review')).to_be_disabled();passed('Completion requires checklist and self-assessment; future review is disabled')
        page.screenshot(path=str(output/'desktop-module.png'),full_page=True)
        key='stm32-practice:stm32f103-practical-ru:v1'
        saved=page.evaluate('(key)=>localStorage.getItem(key)',key)
        assert saved and json.loads(saved)['modules']['L00']['selfTest']
        context.set_offline(False);page.reload();context.set_offline(True)
        expect(page.locator('#sidebar-count')).to_have_text('1 / 14');passed('Progress survives reload in tested browser and origin')
        page.get_by_role('button',name='Мой прогресс').click()
        with page.expect_download() as download:page.locator('#export-progress').click()
        saved_file=output/'exported-progress.json';download.value.save_as(saved_file)
        exported=json.loads(saved_file.read_text());assert exported['format']=='stm32-practice-progress'
        passed('Export produces a valid JSON file')
        page.once('dialog',lambda dialog:dialog.dismiss());page.locator('#reset-progress').click()
        expect(page.locator('#sidebar-count')).to_have_text('1 / 14')
        page.once('dialog',lambda dialog:dialog.accept());page.locator('#reset-progress').click()
        expect(page.locator('#sidebar-count')).to_have_text('0 / 14');passed('Reset cancel and confirm have different verified outcomes')
        with tempfile.TemporaryDirectory() as temporary:
            temporary=Path(temporary)
            for index,bad in enumerate([{'format':exported['format'],'version':0,'courseId':exported['courseId'],'modules':{}},{'format':exported['format'],'version':2,'courseId':exported['courseId'],'modules':{}},{**exported,'courseId':'different-course'},{**exported,'modules':{'L99':{}}}]):
                path=temporary/f'bad-{index}.json';path.write_text(json.dumps(bad))
                page.locator('#import-file').set_input_files(path);expect(page.locator('#import-status')).to_have_class('import-status error')
                expect(page.locator('#sidebar-count')).to_have_text('0 / 14')
            malicious=json.loads(json.dumps(exported));malicious['modules']['L00']['checks']=['<img src=x onerror="window.injected=true">'];path=temporary/'injection.json';path.write_text(json.dumps(malicious))
            page.locator('#import-file').set_input_files(path);expect(page.locator('#import-status')).to_have_class('import-status error')
            assert not page.evaluate('Boolean(window.injected)')
        passed('Old/new versions, other course, unknown modules and injected checkpoints are rejected without mutation')
        page.once('dialog',lambda dialog:dialog.dismiss());page.locator('#import-file').set_input_files(saved_file)
        expect(page.locator('#sidebar-count')).to_have_text('0 / 14')
        page.once('dialog',lambda dialog:dialog.accept());page.locator('#import-file').set_input_files(saved_file)
        expect(page.locator('#sidebar-count')).to_have_text('1 / 14');passed('Valid import cancel and replacement work')
        page.keyboard.press('Escape');expect(page.locator('#progress-dialog')).not_to_be_visible()
        page.get_by_role('button',name='Включить тёмную тему').click();assert page.locator('html').get_attribute('data-theme')=='dark'
        page.screenshot(path=str(output/'dark-module.png'),full_page=True);page.get_by_role('button',name='Включить светлую тему').click();passed('Dialog Escape and light/dark toggle')
        page.set_viewport_size({'width':320,'height':860})
        page.locator('.brand').click();expect(page.locator('.module-card')).to_have_count(14)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output/'mobile-home-320.png'),full_page=True)
        page.locator('#menu-toggle').click();expect(page.locator('#menu-toggle')).to_have_attribute('aria-expanded','true')
        page.keyboard.press('Escape');expect(page.locator('#menu-toggle')).to_have_attribute('aria-expanded','false')
        page.locator('.module-card h3 a').nth(1).click()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output/'mobile-module-320.png'),full_page=True)
        assert page.locator('.code-block').count()>0
        assert page.locator('.article-body').evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)')>=16
        assert page.locator('.article-body pre code').first.evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)')>=13
        first_code=page.locator('.article-body pre code').first.inner_text()
        page.locator('.wrap-code').first.click();expect(page.locator('.wrap-code').first).to_have_attribute('aria-pressed','true')
        assert page.locator('.article-body pre code').first.inner_text()==first_code
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('.wrap-code').first.click();expect(page.locator('.wrap-code').first).to_have_attribute('aria-pressed','false')
        page.locator('.copy-code').first.click();passed('320 px home/module widths, legible body/code sizing, reversible code wrapping, and mobile navigation')
        page.get_by_role('button',name='Мой прогресс').click()
        page.locator('#dialog-theme-toggle').click();expect(page.locator('#dialog-theme-toggle')).to_have_attribute('aria-pressed','true')
        page.locator('#dialog-theme-toggle').click();expect(page.locator('#dialog-theme-toggle')).to_have_attribute('aria-pressed','false')
        page.keyboard.press('Escape');passed('Theme is also reachable in the progress dialog at mobile width')
        # Force both clipboard routes to fail and verify the readable manual fallback.
        page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:()=>Promise.reject(new Error('blocked'))}});document.execCommand=()=>false")
        page.locator('.copy-code').first.click();expect(page.locator('#toast')).to_contain_text('Код выделен')
        assert page.evaluate('getSelection().toString().length>0');passed('Denied clipboard gets selection/manual-copy fallback')
        # Protect unsupported existing storage instead of silently overwriting it.
        future=json.dumps({'format':exported['format'],'version':999,'courseId':exported['courseId'],'modules':{}})
        page.evaluate('([key,value])=>localStorage.setItem(key,value)',[key,future])
        context.set_offline(False);page.reload();context.set_offline(True)
        expect(page.locator('#storage-warning')).to_contain_text('не перезаписан')
        page.locator('[data-checkpoint]').first.check()
        assert page.evaluate('(key)=>localStorage.getItem(key)',key)==future
        page.get_by_role('button',name='Мой прогресс').click()
        with page.expect_download() as recovery_download:page.locator('#recover-progress').click()
        recovery_file=output/'recovery-original.json';recovery_download.value.save_as(recovery_file)
        assert recovery_file.read_text()==future
        passed('Future stored schema is protected from overwrite and can be downloaded verbatim')
        context.close()
        blocked=browser.new_context(viewport={'width':320,'height':860})
        blocked.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Denied','SecurityError')}})")
        blocked_page=blocked.new_page();blocked_page.on('pageerror',lambda error:errors.append(str(error)))
        blocked_page.goto(url);expect(blocked_page.locator('#storage-warning')).to_be_visible()
        blocked_page.locator('.module-card h3 a').first.click();blocked_page.locator('[data-checkpoint]').first.check()
        assert blocked_page.locator('[data-checkpoint]').first.is_checked()
        passed('Disabled storage leaves learning and temporary checklists usable')
        blocked_page.keyboard.press('Control+Home');blocked_page.locator('body').click(position={'x':0,'y':0})
        # Semantics (not a substitute for a screen-reader audit).
        assert blocked_page.locator('main').count()==1 and blocked_page.locator('h1').count()==1
        assert blocked_page.locator('input[type=checkbox]').count()==blocked_page.locator('label:has(input[type=checkbox])').count()
        passed('Main landmark, single page h1 and labelled checkboxes')
        blocked.close();browser.close()
    permitted_document=url.split('#')[0]
    network=[r for r in requests if urlsplit(r['url']).scheme in ('http','https') and not (r['type']=='document' and r['url'].split('#')[0]==permitted_document)]
    report={'kind':'actual-browser-qa','url':url,'checks':checks,'page_errors':errors,'unexpected_network_requests':network,'passed':not errors and not network,'build':build}
    (output/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if errors or network:raise AssertionError(report)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',default=(ROOT/'index.html').as_uri());parser.add_argument('--output',type=Path,default=ROOT/'qa/browser');parser.add_argument('--chromium',default='/usr/bin/chromium');args=parser.parse_args()
    print(json.dumps(run(args.url,args.output,args.chromium),ensure_ascii=False,indent=2))
