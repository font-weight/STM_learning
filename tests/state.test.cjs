'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const S = require('../site/state.js');
const course = {id: 'test-course', modules: [{id: 'L00', track:'core', checkpoints:[{id:'build'}, {id:'explain'}]}, {id:'L01', track:'optional', checkpoints:[{id:'extra'}]}]};
const mod = course.modules[0], now = Date.UTC(2026, 9, 9);
function finished() { let p=S.blank(course); p=S.change(p,mod,'build',true,now); p=S.change(p,mod,'explain',true,now); return S.change(p,mod,'selfTest',true,now); }
test('blank state and core-only statistics',()=>assert.deepEqual(S.stats(S.blank(course),course),{finished:0,core:1,checked:0,total:3,percent:0}));
test('checklists require a separate self-assessment; writes are immutable',()=>{const old=S.blank(course);let p=S.change(old,mod,'build',true,now);p=S.change(p,mod,'explain',true,now);assert.equal(S.complete(S.getModule(p,'L00'),mod),false);assert.deepEqual(old.modules,{});assert.equal(S.complete(finished().modules.L00,mod),true);});
test('completion schedules local reviews on days 1, 3, 7 and 21',()=>{let p=finished();assert.equal(p.modules.L00.review.dueAt,new Date(now+S.DAY).toISOString());p=S.review(p,mod,now);assert.equal(p.modules.L00.review.step,0);p=S.review(p,mod,now+S.DAY);assert.equal(p.modules.L00.review.dueAt,new Date(now+3*S.DAY).toISOString());p=S.review(p,mod,now+3*S.DAY);assert.equal(p.modules.L00.review.dueAt,new Date(now+7*S.DAY).toISOString());p=S.review(p,mod,now+7*S.DAY);assert.equal(p.modules.L00.review.dueAt,new Date(now+21*S.DAY).toISOString());p=S.review(p,mod,now+21*S.DAY);assert.equal(p.modules.L00.review.dueAt,null);assert.equal(p.modules.L00.review.step,4);assert.deepEqual(S.validate(p,course),p);});
test('late reviews preserve spacing rather than enabling four immediate confirmations',()=>{let p=S.review(finished(),mod,now+30*S.DAY);assert.equal(p.modules.L00.review.dueAt,new Date(now+32*S.DAY).toISOString());p=S.review(p,mod,now+30*S.DAY);assert.equal(p.modules.L00.review.step,1);});
test('undo completion also resets associated review schedule',()=>{const p=S.change(finished(),mod,'build',false,now);assert.equal(p.modules.L00.completedAt,null);assert.equal(p.modules.L00.review,null);});
test('export / import round trip',()=>{const p=finished();assert.deepEqual(S.validate(JSON.stringify({...p,exportedAt:new Date(now).toISOString()}),course),p);});
test('reject malformed, oversized, older and newer versions without changing state',()=>{const p=finished();for(const bad of ['!', 'x'.repeat(S.MAX_BYTES+1), {...p,version:0}, {...p,version:2}, {...p,courseId:'other'}, {...p,modules:[]}, {...p,modules:{L99:p.modules.L00}}])assert.throws(()=>S.validate(bad,course));assert.equal(p.modules.L00.selfTest,true);});
test('reject unknown checkpoints, duplicates, dates and inconsistent completion',()=>{for(const alter of [{checks:['<img src=x onerror=alert(1)>']},{checks:['build','build']},{completedAt:'yesterday'},{selfTest:false},{review:null},{review:{step:99,dueAt:null,lastAt:null}}]){const p=finished();Object.assign(p.modules.L00,alter);assert.throws(()=>S.validate(p,course));}});
test('drop extra imported properties; do not retain arbitrary HTML data',()=>{const p=finished();p.evil='<script>evil</script>';p.modules.L00.notes='<img onerror=evil>';const clean=S.validate(p,course);assert.equal(Object.hasOwn(clean,'evil'),false);assert.equal(Object.hasOwn(clean.modules.L00,'notes'),false);});
test('prototype-looking module names rejected',()=>{const p=JSON.stringify(S.blank(course)).replace('"modules":{}','"modules":{"__proto__":{}}');assert.throws(()=>S.validate(p,course));});
test('due reviews and finished core counts',()=>{const p=finished();assert.equal(S.due(p,course,now).length,0);assert.equal(S.due(p,course,now+S.DAY).length,1);assert.equal(S.stats(p,course).percent,100);});

// A deliberately small, dependency-free DOM contract harness. It exercises the
// real app event handlers; it does not render CSS or replace browser/a11y QA.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const decode = value => String(value).replace(/&(amp|lt|gt|quot|#39);/g, (_, key) => ({amp:'&',lt:'<',gt:'>',quot:'"','#39':"'"}[key]));
class ContractNode {
  constructor(tag = 'div', attrs = {}, doc = null) { this.tagName=tag.toUpperCase();this.attrs={...attrs};this.doc=doc;this.children=[];this.listeners={};this.parentElement=null;this._text='';this._checked=Object.hasOwn(attrs,'checked');this.value=attrs.value||'';this.style={};this.files=[]; }
  get classList() { const node=this;return {contains:n=>(node.attrs.class||'').split(/\s+/).includes(n),add(...names){const set=new Set((node.attrs.class||'').split(/\s+/).filter(Boolean));names.forEach(n=>set.add(n));node.attrs.class=[...set].join(' ');},remove(...names){node.attrs.class=(node.attrs.class||'').split(/\s+/).filter(n=>!names.includes(n)).join(' ');},toggle(n,force){const yes=force===undefined?!this.contains(n):force;if(yes)this.add(n);else this.remove(n);return yes;}}; }
  get dataset() { const node=this;return new Proxy({}, {get:(_,key)=>node.attrs['data-'+key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())],set:(_,key,value)=>{node.attrs['data-'+key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())]=String(value);return true;}}); }
  get hidden(){return Object.hasOwn(this.attrs,'hidden');} set hidden(value){if(value)this.attrs.hidden='';else delete this.attrs.hidden;}
  get checked(){return this._checked;} set checked(value){this._checked=Boolean(value);}
  get open(){return Object.hasOwn(this.attrs,'open');} set open(value){if(value)this.attrs.open='';else delete this.attrs.open;}
  get isConnected(){return this.doc && this.doc.documentElement.contains(this);}
  get nextElementSibling(){const peers=this.parentElement?.children||[];return peers.slice(peers.indexOf(this)+1).find(n=>!n.tagName.startsWith('#'))||null;}
  setAttribute(name,value){this.attrs[name]=String(value);} getAttribute(name){return Object.hasOwn(this.attrs,name)?this.attrs[name]:null;}
  get textContent(){return this._text+this.children.map(n=>n.textContent).join('');} set textContent(value){this._text=String(value);this.children=[];}
  set innerHTML(value){this._html=String(value);this._text='';this.children=[];parseFragment(String(value),this,this.doc);} get innerHTML(){return this._html||'';}
  append(node){node.parentElement=this;node.doc=this.doc;this.children.push(node);}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);this.parentElement=null;}
  contains(node){return this===node || this.children.some(child=>child.contains(node));}
  matches(selector){
    if(selector.startsWith('#'))return this.attrs.id===selector.slice(1);
    if(selector.startsWith('.'))return selector.slice(1).split('.').every(c=>this.classList.contains(c));
    const match=/^([a-zA-Z0-9-]+)?(?:\[([^=\]^]+)(\^?=)?["']?([^\]"']*)["']?\])?$/.exec(selector);
    if(!match)throw new Error('Unsupported test selector '+selector);
    if(match[1] && this.tagName!==match[1].toUpperCase())return false;
    if(!match[2])return true;
    const actual=this.getAttribute(match[2]);
    return match[3]==='='?actual===match[4]:match[3]==='^='?actual!==null&&actual.startsWith(match[4]):actual!==null;
  }
  querySelectorAll(selector){const out=[];for(const n of this.children){if(n.matches(selector))out.push(n);out.push(...n.querySelectorAll(selector));}return out;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){for(let n=this;n;n=n.parentElement)if(n.matches(selector))return n;return null;}
  addEventListener(name,handler){(this.listeners[name]||=[]).push(handler);}
  async trigger(name,extra={}){const event={target:this,preventDefault(){this.defaultPrevented=true;},...extra};for(const handler of this.listeners[name]||[])await handler(event);if(name==='click')for(const handler of this.doc.listeners.click||[])await handler(event);return event;}
  focus(){this.doc.activeElement=this;} scrollIntoView(){this.doc.scrolledTo=this;}
  getClientRects(){for(let n=this;n;n=n.parentElement)if(n.hidden)return [];return [{}];}
  showModal(){this.open=true;} close(){this.open=false;} select(){this.doc.selected=this.value;}
  click(){if(this.download){this.doc.downloads.push({name:this.download,url:this.href});}return this.trigger('click');}
}
function parseFragment(source,parent,doc){
  const voids=new Set(['INPUT','BR','HR','META','LINK','IMG','SOURCE']);const stack=[parent];
  for(const token of source.match(/<!--[\s\S]*?-->|<\/?[A-Za-z][^>]*>|[^<]+/g)||[]){
    if(token.startsWith('<!--'))continue;
    if(token.startsWith('</')){const tag=token.slice(2,-1).trim().toUpperCase();if(stack.length>1&&stack.at(-1).tagName===tag)stack.pop();continue;}
    if(token.startsWith('<')){
      const tag=/^<([\w-]+)/.exec(token)[1];const attrs={};
      const tail=token.slice(tag.length+1,-1);
      for(const attr of tail.matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))attrs[attr[1]]=decode(attr[2]??attr[3]??attr[4]??'');
      const node=new ContractNode(tag,attrs,doc);stack.at(-1).append(node);if(!voids.has(node.tagName)&&!token.endsWith('/>'))stack.push(node);
    }else {const text=new ContractNode('#text',{},doc);text._text=decode(token);stack.at(-1).append(text);}
  }
}
function readerDOM({stored=null,denyStorage=false,width=1440,hash='#home',writeDenied=false,deferFrames=false,modelContext,contextGetter,noAbortController=false}={}){
  const doc={listeners:{},downloads:[],activeElement:null};
  if(contextGetter)Object.defineProperty(doc,'modelContext',{get:contextGetter});else if(modelContext!==undefined)doc.modelContext=modelContext;
  doc.documentElement=new ContractNode('html',{},doc);doc.body=new ContractNode('body',{},doc);doc.documentElement.append(doc.body);
  doc.querySelector=s=>doc.documentElement.querySelector(s);doc.querySelectorAll=s=>doc.documentElement.querySelectorAll(s);doc.getElementById=id=>doc.querySelector('#'+id);doc.addEventListener=(name,handler)=>(doc.listeners[name]||=[]).push(handler);doc.createElement=tag=>new ContractNode(tag,{},doc);doc.execCommand=()=>false;
  doc.createRange=()=>({selectNodeContents(node){doc.selected=node.textContent;}});
  const template=fs.readFileSync(path.join(__dirname,'../site/index.template.html'),'utf8');
  parseFragment(template.match(/<body>([\s\S]*?)<script id="course-data"/)[1],doc.body,doc);
  const data=new ContractNode('script',{id:'course-data'},doc);doc.body.append(data);
  const fixture={id:course.id,build:'contract-test',modules:course.modules.map((m,i)=>({...m,number:i,title:'Module '+i,summary:'Build and measure',gate:'Observable result',duration:'2 ч',hours:2,path:'docs/labs/'+i+'.md',prerequisites:[],review_prompts:['What did you predict?','How did you verify it?'],html:'<span class="source-title anchor-target" id="article-title"></span><h2 id="article-experiment">Experiment</h2><details class="lesson-hint"><summary>Reveal after an attempt</summary><div><h3 id="article-feedback">Feedback</h3><p>Hidden explanation</p></div></details><div class="code-block"><div class="code-actions"><button class="wrap-code" aria-pressed="false">Перенос строк</button><button class="copy-code">Копировать</button></div><pre><code>line one\nline two</code></pre></div>',headings:[{id:'title',level:1,title:'Module '+i},{id:'experiment',level:2,title:'Experiment'}],searchText:'gpio uart'})),documents:[{path:'docs/guide.md',title:'Guide',html:'<h2 id="article-guide-start">Guide section</h2><p>Guide content</p>',headings:[{id:'guide-start',level:2,title:'Guide section'}]}]};
  data.textContent=JSON.stringify(fixture);
  const key='stm32-practice:'+course.id+':v1';const values=new Map(stored===null?[]:[[key,stored]]);
  const localStorage={getItem(k){if(denyStorage)throw new Error('Denied');return values.get(k)??null;},setItem(k,v){if(denyStorage||writeDenied)throw new Error('Denied');values.set(k,String(v));},removeItem(k){if(denyStorage||writeDenied)throw new Error('Denied');values.delete(k);}};
  const events={};const answers=[];const blobs=new Map();const frames=[];
  const win={CourseState:S,scrollY:0,isSecureContext:false,confirm:()=>answers.length?answers.shift():true,addEventListener:(name,handler)=>(events[name]||=[]).push(handler),scrollTo(){},getSelection:()=>({removeAllRanges(){doc.selected='';},addRange(){}})};
  const loc={hash};
  const globals={document:doc,window:win,location:loc,localStorage,navigator:{},matchMedia:q=>({matches:q.includes('1251')?width>=1251:false}),requestAnimationFrame:handler=>deferFrames?frames.push(handler):handler(),setTimeout:()=>1,clearTimeout(){},Blob,URL:{createObjectURL(blob){const url='blob:test/'+blobs.size;blobs.set(url,blob);return url;},revokeObjectURL(){}},console};
  if(!noAbortController)globals.AbortController=AbortController;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../site/app.js'),'utf8'),globals,{filename:'site/app.js'});
  return {doc,values,key,answers,blobs,fixture,get hash(){return loc.hash;},async dispatch(name,event={}){for(const handler of events[name]||[])await handler(event);},flushFrames(){while(frames.length)frames.shift()();},async navigate(hash){loc.hash=hash;for(const handler of events.hashchange||[])await handler();},async storage(value){for(const handler of events.storage||[])await handler({key,newValue:value});},async click(selector){const node=doc.querySelector(selector);assert.ok(node,'Expected '+selector);await node.trigger('click');},async check(field,value=true){const node=doc.querySelector('[data-checkpoint="'+field+'"]');assert.ok(node);node.checked=value;await node.trigger('change');}};
}

test('DOM contract: recall route hides material, leaves marks unchanged, and returns cleanly',async()=>{
  const r=readerDOM();assert.equal(r.doc.querySelectorAll('.module-card').length,2);
  await r.navigate('#recall/L00');
  assert.equal(r.doc.querySelector('#recall-panel').hidden,false);
  assert.equal(r.doc.querySelector('.lesson-layout').hidden,true);
  assert.equal(r.doc.querySelector('.learning-check').hidden,true);
  assert.equal(r.doc.activeElement,r.doc.querySelector('#recall-title'));
  assert.equal(r.values.has(r.key),false);
  await r.navigate('#module/L00');
  assert.equal(r.doc.querySelector('.lesson-layout').hidden,false);
  assert.equal(r.doc.querySelector('#recall-panel').hidden,true);
  assert.equal(r.doc.querySelector('.lesson-hint').open,false);
  await r.navigate('#recall/L00');await r.navigate('#module/L01');
  assert.equal(r.doc.querySelector('.lesson-layout').hidden,false);
  assert.equal(r.doc.querySelector('#module-completion-status').textContent,'0 / 1 отметок практики');
});
test('DOM contract: section route opens its hint and reader-check route reaches evidence',async()=>{
  const r=readerDOM({hash:'#module/L00'});
  await r.navigate('#section/module/L00/feedback');
  assert.equal(r.doc.querySelector('.lesson-hint').open,true);
  assert.equal(r.doc.activeElement,r.doc.querySelector('#article-feedback'));
  await r.navigate('#section/module/L00/reader-checks');
  assert.equal(r.doc.activeElement,r.doc.querySelector('.learning-check'));
  assert.equal(r.doc.querySelector('.lesson-layout').hidden,false);
});
test('DOM contract: wrapping code changes presentation only and can be reversed',async()=>{
  const r=readerDOM({hash:'#module/L00'});const original=r.doc.querySelector('code').textContent;
  await r.click('.wrap-code');assert.equal(r.doc.querySelector('.wrap-code').getAttribute('aria-pressed'),'true');assert.equal(r.doc.querySelector('.code-block').classList.contains('is-wrapped'),true);
  assert.equal(r.doc.querySelector('code').textContent,original);
  await r.click('.wrap-code');assert.equal(r.doc.querySelector('.wrap-code').getAttribute('aria-pressed'),'false');assert.equal(r.doc.querySelector('.code-block').classList.contains('is-wrapped'),false);
});
test('DOM contract: v1 data imports, exports and survives recall mode without migration',async()=>{
  const saved=finished();const r=readerDOM({stored:JSON.stringify(saved),hash:'#module/L00'});
  assert.equal(r.doc.querySelector('#sidebar-count').textContent,'1 / 1');
  await r.navigate('#recall/L00');await r.navigate('#module/L00');
  assert.deepEqual(JSON.parse(r.values.get(r.key)),saved);
  await r.click('#export-progress');assert.equal(r.doc.downloads.length,1);
  const blob=r.blobs.get(r.doc.downloads[0].url);const exported=JSON.parse(await blob.text());
  assert.deepEqual(S.validate(exported,course),saved);assert.equal(exported.version,1);
  r.answers.push(false);await r.click('#reset-progress');assert.deepEqual(JSON.parse(r.values.get(r.key)),saved);
  r.answers.push(true);await r.click('#reset-progress');assert.deepEqual(JSON.parse(r.values.get(r.key)),S.blank(course));
  const upload=r.doc.querySelector('#import-file');upload.files=[{size:100,text:async()=>JSON.stringify(exported)}];r.answers.push(false);await upload.trigger('change');assert.deepEqual(JSON.parse(r.values.get(r.key)),S.blank(course));
  upload.files=[{size:100,text:async()=>JSON.stringify(exported)}];r.answers.push(true);await upload.trigger('change');assert.deepEqual(JSON.parse(r.values.get(r.key)),saved);
});
test('DOM contract: denied and incompatible storage keeps temporary changes honest',async()=>{
  for(const options of [{denyStorage:true},{writeDenied:true}]){
    const r=readerDOM({...options,hash:'#module/L00'});await r.check('build');
    assert.equal(r.doc.querySelector('[data-checkpoint="build"]').checked,true);
    assert.match(r.doc.querySelector('#storage-status').textContent,/временные/);
    assert.equal(r.values.has(r.key),false);
  }
  const raw=JSON.stringify({...S.blank(course),version:999});const r=readerDOM({stored:raw,hash:'#module/L00'});
  await r.check('build');assert.equal(r.values.get(r.key),raw);assert.match(r.doc.querySelector('#storage-status').textContent,/приостановлено/);
  await r.click('#recover-progress');assert.equal(await r.blobs.get(r.doc.downloads[0].url).text(),raw);
});
test('DOM contract: compact contents default closed and malformed routes stay usable',async()=>{
  const r=readerDOM({width:320,hash:'#module/L00'});assert.equal(r.doc.querySelector('.toc').open,false);
  await r.navigate('#module/%E0%A4%A');assert.match(r.doc.querySelector('h1').textContent,/Такой страницы нет/);
  await r.navigate('#recall/does-not-exist');assert.match(r.doc.querySelector('h1').textContent,/Такой страницы нет/);
  await r.navigate('#home');assert.equal(r.doc.querySelectorAll('.module-card').length,2);
});

test('DOM contract: a newer route wins over a queued old section focus',async()=>{
  const r=readerDOM({deferFrames:true});r.flushFrames();
  await r.navigate('#section/module/L00/feedback');await r.navigate('#module/L01');r.flushFrames();
  assert.equal(r.doc.activeElement,r.doc.querySelector('#main'));
  assert.equal(r.doc.querySelector('.lesson-hint').open,false);
  await r.navigate('#recall/L00');await r.navigate('#home');r.flushFrames();
  assert.equal(r.doc.querySelectorAll('.module-card').length,2);
  assert.equal(r.doc.activeElement,r.doc.querySelector('#main'));
});
test('DOM contract: theme can be changed from the mobile progress dialog',async()=>{
  const r=readerDOM({width:320});assert.equal(r.doc.documentElement.dataset.theme,'light');
  await r.click('#dialog-theme-toggle');assert.equal(r.doc.documentElement.dataset.theme,'dark');
  assert.equal(r.doc.querySelector('#dialog-theme-toggle').getAttribute('aria-pressed'),'true');
  assert.equal(r.values.get('stm32-practice:theme'),'dark');
  await r.click('#dialog-theme-toggle');assert.equal(r.doc.documentElement.dataset.theme,'light');
});

test('DOM contract: document routes keep contents before readable content and preserve anchors',async()=>{
  const r=readerDOM({width:320});await r.navigate('#document/docs/guide.md');
  assert.equal(r.doc.querySelector('h1').textContent,'Guide');
  assert.match(r.doc.querySelector('.article-body').textContent,/Guide content/);
  assert.equal(r.doc.querySelector('.document-layout').children[0].tagName,'ASIDE');
  assert.equal(r.doc.querySelector('.toc').open,false);
  await r.navigate('#section/document/docs/guide.md/guide-start');
  assert.equal(r.doc.activeElement,r.doc.querySelector('#article-guide-start'));
});

// Optional WebMCP tests use a native Node registry double and the DOM contract
// harness above. These do not validate a real browser or WebMCP implementation.
function registryDouble() {
  const tools=new Map(),registrations=[];
  return {tools,registrations,registerTool(tool,options){
    assert.equal(tools.has(tool.name),false,'Duplicate active registration');
    tools.set(tool.name,tool);registrations.push({tool,options});
    options.signal.addEventListener('abort',()=>tools.delete(tool.name),{once:true});
  }};
}
const plain=value=>JSON.parse(JSON.stringify(value));

test('DOM contract: functional home summary reflects only actual local marks',async()=>{
  const r=readerDOM();const summary=r.doc.querySelector('.learning-summary');
  assert.ok(summary);assert.equal(summary.getAttribute('aria-hidden'),null);
  assert.equal(summary.querySelector('strong').textContent,'0');
  assert.equal(summary.querySelector('progress').getAttribute('value'),'0');
  assert.match(summary.textContent,/самоотчёт/);
  assert.equal(summary.querySelector('a').getAttribute('href'),'#module/L00');
  await r.navigate('#module/L00');await r.check('build');await r.check('explain');await r.check('selfTest');await r.navigate('#home');
  assert.equal(r.doc.querySelector('.learning-summary').querySelector('strong').textContent,'1');
  assert.equal(r.doc.querySelector('.learning-summary').querySelector('progress').getAttribute('value'),'1');
  assert.match(r.doc.querySelector('.learning-summary').textContent,/Вернуться к практике/);
});
test('DOM contract: shell controls have descriptive text without decorative arrows',async()=>{
  const r=readerDOM();
  for(const hash of ['#home','#module/L00','#recall/L00','#document/docs/guide.md']){
    await r.navigate(hash);
    for(const control of [...r.doc.querySelectorAll('a'),...r.doc.querySelectorAll('button')]){
      assert.doesNotMatch(control.textContent,/[↗→←↑↓]/,hash+': '+control.textContent);
    }
  }
  assert.match(r.doc.querySelector('.page-footer').textContent,/Прогресс в этом браузере/);
  const template=fs.readFileSync(path.join(__dirname,'../site/index.template.html'),'utf8');
  assert.match(template,/<link rel="icon" type="image\/svg\+xml" href="data:image\/svg\+xml,%3Csvg/);
  assert.doesNotMatch(template,/Без аккаунта/);
});
test('WebMCP native double: only three bounded metadata/navigation tools register once',async()=>{
  const registry=registryDouble(),r=readerDOM({modelContext:registry});
  assert.deepEqual([...registry.tools.keys()],['read_course_curriculum','navigate_course','start_course_recall']);
  await r.dispatch('pageshow');assert.equal(registry.registrations.length,3);
  assert.equal(new Set(registry.registrations.map(x=>x.options.signal)).size,1);
  for(const {tool,options} of registry.registrations){
    assert.equal(options.signal.aborted,false);assert.equal(tool.inputSchema.type,'object');
    assert.equal(tool.inputSchema.additionalProperties,false);
    assert.equal(tool.annotations.untrustedContentHint,false);
    assert.equal(tool.annotations.readOnlyHint,tool.name==='read_course_curriculum');
  }
});
test('WebMCP native double: curriculum excludes progress and hidden lesson content even during recall',async()=>{
  const registry=registryDouble(),raw=JSON.stringify(finished()),r=readerDOM({modelContext:registry,stored:raw,hash:'#recall/L00'});
  const read=registry.tools.get('read_course_curriculum').execute;
  const result=plain(await read({}));
  assert.deepEqual(Object.keys(result).sort(),['courseId','modules','resources']);
  assert.deepEqual(Object.keys(result.modules[0]).sort(),['duration','id','number','prerequisites','summary','title','track']);
  assert.deepEqual(Object.keys(result.resources[0]).sort(),['path','title']);
  assert.deepEqual(result.modules.map(m=>m.id),['L00','L01']);
  assert.equal(r.values.get(r.key),raw);assert.equal(r.hash,'#recall/L00');
  assert.equal(r.doc.querySelector('.lesson-layout').hidden,true);
  assert.doesNotMatch(JSON.stringify(result),/Hidden explanation|checks|selfTest|review|completedAt|performedAt/);
  result.modules[0].prerequisites.push('wrong');result.modules[0].title='changed';
  const fresh=plain(await read({}));assert.equal(fresh.modules[0].title,'Module 0');assert.deepEqual(fresh.modules[0].prerequisites,[]);
});
test('WebMCP native double: navigation updates the same visible page and focus without progress writes',async()=>{
  const registry=registryDouble(),raw=JSON.stringify(finished()),r=readerDOM({modelContext:registry,stored:raw});
  const nav=registry.tools.get('navigate_course').execute;
  assert.deepEqual(plain(await nav({view:'module',moduleId:'L00'})),{view:'module',moduleId:'L00',title:'Module 0'});
  assert.equal(r.hash,'#module/L00');assert.equal(r.doc.querySelector('h1').textContent,'Module 0');
  assert.equal(r.doc.activeElement,r.doc.querySelector('#main'));
  assert.equal(r.doc.querySelector('.lesson-layout').hidden,false);
  const main=r.doc.querySelector('#main');const content=main.innerHTML;
  await r.dispatch('hashchange');assert.equal(main.innerHTML,content);
  assert.deepEqual(plain(await nav({view:'document',documentPath:'docs/guide.md'})),{view:'document',documentPath:'docs/guide.md',title:'Guide'});
  assert.equal(r.doc.querySelector('h1').textContent,'Guide');
  assert.deepEqual(plain(await nav({view:'home'})),{view:'home'});
  assert.equal(r.doc.querySelectorAll('.module-card').length,2);assert.equal(r.values.get(r.key),raw);
});
test('WebMCP native double: starting recall only opens the existing no-hints view',async()=>{
  const registry=registryDouble(),raw=JSON.stringify(finished()),r=readerDOM({modelContext:registry,stored:raw});
  const result=plain(await registry.tools.get('start_course_recall').execute({moduleId:'L00'}));
  assert.deepEqual(result,{view:'recall',moduleId:'L00',title:'Module 0'});
  assert.equal(r.hash,'#recall/L00');assert.equal(r.doc.querySelector('#recall-panel').hidden,false);
  assert.equal(r.doc.querySelector('.lesson-layout').hidden,true);assert.equal(r.doc.querySelector('.learning-check').hidden,true);
  assert.equal(r.doc.activeElement,r.doc.querySelector('#recall-title'));
  assert.equal(r.values.get(r.key),raw);
});
test('WebMCP native double: invalid arguments fail before navigation or stored data change',async()=>{
  const registry=registryDouble(),raw=JSON.stringify(finished()),r=readerDOM({modelContext:registry,stored:raw});
  const read=registry.tools.get('read_course_curriculum').execute,nav=registry.tools.get('navigate_course').execute,recall=registry.tools.get('start_course_recall').execute;
  const invalid=[
    [read,null],[read,[]],[read,{progress:true}],
    [nav,{}],[nav,{view:'reset'}],[nav,{view:'home',moduleId:'L00'}],
    [nav,{view:'module'}],[nav,{view:'module',moduleId:0}],[nav,{view:'module',moduleId:'L99'}],
    [nav,{view:'module',moduleId:'L00',documentPath:'docs/guide.md'}],
    [nav,{view:'document',documentPath:'https://example.com'}],[nav,{view:'document',documentPath:'../private.json'}],
    [nav,{view:'document',documentPath:'docs/guide.md',extra:true}],
    [recall,{}],[recall,{moduleId:'L99'}],[recall,{moduleId:'L00',complete:true}],
    [recall,Object.create({moduleId:'L00'})],[recall,{moduleId:'x'.repeat(129)}]
  ];
  for(const [execute,input] of invalid){await assert.rejects(async()=>execute(input));assert.equal(r.hash,'#home');assert.equal(r.values.get(r.key),raw);}
});
test('WebMCP native double: navigation result waits for visible frame and rejects a superseded route',async()=>{
  const registry=registryDouble(),r=readerDOM({modelContext:registry,deferFrames:true});r.flushFrames();
  const nav=registry.tools.get('navigate_course').execute;
  let resolved=false;const first=nav({view:'module',moduleId:'L00'}).then(result=>{resolved=true;return result;});
  await Promise.resolve();assert.equal(resolved,false);r.flushFrames();await first;assert.equal(resolved,true);
  const stale=nav({view:'module',moduleId:'L01'});await r.navigate('#home');r.flushFrames();
  await assert.rejects(stale,/Переход отменён/);assert.equal(r.hash,'#home');
});
test('WebMCP native double: no support, absent AbortController, and throwing accessors keep reader usable',()=>{
  for(const options of [{},{modelContext:{}},{modelContext:{registerTool:0}},{modelContext:registryDouble(),noAbortController:true},{contextGetter(){throw new Error('Unavailable');}},{modelContext:{get registerTool(){throw new Error('Unavailable');}}}]){
    const r=readerDOM(options);assert.equal(r.doc.querySelectorAll('.module-card').length,2);assert.equal(r.values.has(r.key),false);
  }
});
test('WebMCP native double: synchronous and asynchronous registration errors are contained',async()=>{
  for(const fail of [()=>{throw new Error('Registration denied');},()=>Promise.reject(new Error('Registration denied'))]){
    const r=readerDOM({modelContext:{registerTool:fail}});await Promise.resolve();await Promise.resolve();
    assert.equal(r.doc.querySelectorAll('.module-card').length,2);
    await r.navigate('#module/L00');assert.equal(r.doc.querySelector('h1').textContent,'Module 0');
  }
});
test('WebMCP native double: lifecycle unregisters, rejects stale handles, and restores after page return',async()=>{
  const registry=registryDouble(),r=readerDOM({modelContext:registry});
  const old=registry.tools.get('start_course_recall');await r.dispatch('pagehide',{persisted:true});
  assert.equal(registry.tools.size,0);assert.ok(registry.registrations.every(x=>x.options.signal.aborted));
  await assert.rejects(async()=>old.execute({moduleId:'L00'}),/Страница уже закрыта/);
  await r.dispatch('pageshow',{persisted:true});assert.equal(registry.tools.size,3);assert.equal(registry.registrations.length,6);
  await registry.tools.get('start_course_recall').execute({moduleId:'L00'});assert.equal(r.hash,'#recall/L00');
});
