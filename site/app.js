(function () {
  'use strict';
  const course = JSON.parse(document.getElementById('course-data').textContent);
  const S = window.CourseState;
  const $ = selector => document.querySelector(selector);
  const escape = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const moduleById = new Map(course.modules.map(m => [m.id,m]));
  const docByPath = new Map(course.documents.map(d => [d.path,d]));
  const STORAGE_KEY = 'stm32-practice:' + course.id + ':v1';
  const THEME_KEY = 'stm32-practice:theme';
  let state = S.blank(course);
  let storageBlocked = false;
  let recoveryRaw = null;
  let storageMessage = '';
  let current = {type:'home'};
  let toastTimer;
  let filter = 'all', query = '';
  const number = m => String(m.number).padStart(2,'0');
  const moduleHref = m => '#module/' + encodeURIComponent(m.id);
  const documentHref = path => '#document/' + encodeURI(path);
  const hasExtension = m => m.track === 'optional' || Number(m.optional_hours || 0) > 0;
  const date = value => new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value));
  const isComplete = m => S.complete(S.getModule(state,m.id),m);
  const checkpointCount = m => S.getModule(state,m.id).checks.length;

  function warn(text) {
    storageMessage = text;
    const box = $('#storage-warning');
    box.textContent = text;
    box.hidden = !text;
    $('#dialog-storage-warning').textContent=text;
    $('#dialog-storage-warning').hidden=!text;
    $('#recover-progress').hidden=recoveryRaw===null;
  }
  function notify(text) {
    const el = $('#toast');
    el.textContent = text;
    el.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('visible'),6000);
  }
  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw !== null) {
        try { state = S.validate(raw,course); }
        catch (error) {
          storageBlocked = true;
          recoveryRaw = raw;
          warn('Сохранённый прогресс несовместим или повреждён. Он не перезаписан. Новые отметки временные: импортируйте совместимый файл или подтвердите сброс. ' + error.message);
          return;
        }
      }
      // A successful read alone does not prove writing is allowed (private mode/quota).
      const probe = STORAGE_KEY + ':probe';
      localStorage.setItem(probe,'1');
      localStorage.removeItem(probe);
    } catch (_) {
      warn('Браузер не разрешает сохранять прогресс здесь. Отметки работают до закрытия страницы. Используйте «Мой прогресс → Экспорт JSON» для сохранения.');
    }
  }
  function save() {
    if (storageBlocked) return false;
    try {
      localStorage.setItem(STORAGE_KEY,JSON.stringify(state));
      recoveryRaw=null;
      $('#recover-progress').hidden=true;
      if (storageMessage) warn('');
      return true;
    } catch (_) {
      warn('Не удалось сохранить отметки в браузере. Они остаются на этой странице до её закрытия. Сохраните копию через «Экспорт JSON».');
      return false;
    }
  }
  function theme() {
    let selected;
    try { selected = localStorage.getItem(THEME_KEY); } catch (_) { /* file:// may deny storage */ }
    if (selected !== 'light' && selected !== 'dark') selected = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark':'light';
    setTheme(selected,false);
  }
  function setTheme(value,persist) {
    document.documentElement.dataset.theme = value;
    $('.theme-toggle').setAttribute('aria-label',value === 'dark' ? 'Включить светлую тему':'Включить тёмную тему');
    if (persist) { try {localStorage.setItem(THEME_KEY,value);} catch (_) {notify('Тема изменена только для текущей страницы.');} }
  }
  function refreshNavigation() {
    $('#module-nav').innerHTML = course.modules.map(m => '<li class="' + (isComplete(m)?'done':'') + '"><a href="' + moduleHref(m) + '"' + (current.type==='module'&&current.id===m.id?' aria-current="page"':'') + '><span class="nav-number" aria-hidden="true">' + (isComplete(m)?'✓':number(m)) + '</span><span><span class="visually-hidden">Лаборатория ' + number(m) + '. ' + (isComplete(m)?'Отмечена выполненной. ':'') + '</span>' + escape(m.title) + (m.track==='optional'?'<span class="nav-optional">По желанию</span>':'') + '</span></a></li>').join('');
    $('#resource-nav').innerHTML = course.documents.filter(d=>d.path!=='README.md').slice(0,11).map(d=>'<a href="' + documentHref(d.path) + '"' + (current.type==='document'&&current.path===d.path?' aria-current="page"':'') + '>' + escape(d.title) + '</a>').join('');
    $('.overview-link').setAttribute('aria-current',current.type==='home'?'page':'false');
    const stats = S.stats(state,course);
    $('#sidebar-count').textContent = stats.finished+' / '+stats.core;
    $('#sidebar-progress').max = stats.core;
    $('#sidebar-progress').value = stats.finished;
    $('#dialog-stats').textContent = stats.finished+' из '+stats.core+' модулей основного маршрута отмечены выполненными. Проверок: '+stats.checked+' / '+stats.total+'.';
  }
  function boardArt() {
    return '<div class="hero-art" aria-hidden="true"><span class="board-badge">CORTEX–M3</span><svg class="board" viewBox="0 0 350 235" xmlns="http://www.w3.org/2000/svg"><g fill="none" stroke="#a4bbaa" stroke-width="1"><path d="M0 140h35l20-20h30M350 120h-30l-20 25h-20M190 0v22l-10 12v25M80 235v-30l20-18M310 235v-50l-20-20"/><circle cx="35" cy="140" r="3"/><circle cx="320" cy="120" r="3"/></g><rect x="46" y="57" width="262" height="127" rx="6" fill="#316b81"/><rect x="51" y="62" width="252" height="117" rx="3" fill="#245b70" stroke="#558a94"/><g stroke="#a2bcb9" stroke-width="1" opacity=".65"><path d="M91 75h35l25 25M85 84h33l26 26M82 169h36l26-32M88 160h22l26-25M187 87l13-13h82M198 98l21-13h66M205 135l30 30h48M207 128l21 25h58M218 113h67"/></g><g fill="#bcad74">' + Array.from({length:20},(_,i)=>'<rect x="'+(61+i*12)+'" y="49" width="5" height="17" rx="1"/><rect x="'+(61+i*12)+'" y="176" width="5" height="17" rx="1"/>').join('') + '</g><rect x="127" y="78" width="87" height="84" rx="4" fill="#1a2d32"/><g stroke="#afc2be" stroke-width="3">' + Array.from({length:10},(_,i)=>'<path d="M'+(134+i*8)+' 71v7M'+(134+i*8)+' 162v7M120 '+(85+i*8)+'h7M214 '+(85+i*8)+'h7"/>').join('') + '</g><text x="170" y="114" text-anchor="middle" fill="#d8e1d7" font-family="monospace" font-size="10">STM32</text><text x="170" y="129" text-anchor="middle" fill="#8ca5a0" font-family="monospace" font-size="7">F103C8T6</text><circle cx="136" cy="152" r="2" fill="#788f8b"/><rect x="38" y="103" width="33" height="38" rx="3" fill="#9badaf"/><rect x="38" y="109" width="24" height="26" rx="2" fill="#24383c"/><rect x="251" y="97" width="26" height="17" rx="3" fill="#aeb9a4"/><rect x="83" y="107" width="15" height="24" rx="3" fill="#c1c8b4"/><rect x="85" y="150" width="18" height="12" rx="2" fill="#17353b"/><rect x="252" y="135" width="14" height="10" rx="1" fill="#ed9a54"/><rect x="270" y="135" width="9" height="10" rx="1" fill="#91c98e"/><text x="103" y="175" fill="#bcdbd4" font-family="monospace" font-size="6">BLUE PILL · STM32F103</text></svg><span class="board-label">GPIO / TIM / ADC / DMA</span></div>';
  }
  function home() {
    const next = course.modules.find(m=>m.track!=='optional'&&!isComplete(m)) || course.modules[0];
    const started = Object.keys(state.modules).some(id=>state.modules[id].checks.length>0 || state.modules[id].selfTest);
    const allDone = S.stats(state,course).finished === S.stats(state,course).core;
    const extra = Number(course.optional_extension_hours||0)+Number(course.optional_module_hours||0);
    const firstLink = docByPath.has('docs/START_HERE.md') ? documentHref('docs/START_HERE.md') : moduleHref(course.modules[0]);
    const resources = course.documents.filter(d=>d.path!=='README.md');
    $('#main').innerHTML = '<section class="hero"><div><div class="eyebrow">Практический маршрут · для Arduino / AVR</div><h1>От первого blink<br>к <span>своему устройству.</span></h1><p class="hero-lead">Освойте STM32F103 руками: отладчик, периферия и измерения. В финале соберите собственный измеритель с консолью и журналом данных.</p><div class="hero-buttons"><a class="button button-primary" href="' + (started?moduleHref(next):firstLink) + '">' + (allDone?'Вернуться к практике':started?'Продолжить · '+number(next):'Начать с настройки') + '<span aria-hidden="true">↗</span></a><a class="button button-secondary" href="#route" data-scroll="route">Посмотреть маршрут <span aria-hidden="true">↓</span></a></div><div class="hero-meta"><span><strong>' + course.modules.length + '</strong> лабораторий</span><span><strong>≈ '+escape(course.core_hours||'48')+' ч</strong> основы</span><span><strong>60–90 мин</strong> на сессию</span></div></div>' + boardArt() + '</section><section class="start-strip"><div><span class="mini-label">Первый шаг · лаборатория 00</span><h2>Сначала докажите, что управляете платой.</h2><p>Проверьте питание и SWD, соберите проект, прошейте Blue Pill и остановите его в отладчике. Затем переходите к периферии.</p></div><a class="button button-secondary" href="'+moduleHref(course.modules[0])+'">Открыть лабораторию 00 <span aria-hidden="true">→</span></a></section><div class="practice-loop" aria-label="Как устроена практика"><div class="loop-item"><span class="loop-number">01 / СДЕЛАТЬ</span><h3>Собрать и измерить</h3><p>Получите наблюдаемый результат на своей плате.</p></div><div class="loop-item"><span class="loop-number">02 / РАЗОБРАТЬСЯ</span><h3>Найти причину ошибки</h3><p>Безопасно измените один параметр. Объясните, что произошло.</p></div><div class="loop-item"><span class="loop-number">03 / ЗАКРЕПИТЬ</span><h3>Повторить без подсказки</h3><p>Восстановите ключевой шаг и перенесите навык в новую задачу.</p></div></div><div id="home-reviews"></div><section id="route"><div class="section-heading"><div><h2>Ваш маршрут</h2><p>Идите по порядку или вернитесь к нужному навыку.' + (extra?' Расширения добавят до '+extra+' ч.':'') + '</p></div><span class="section-caption">От подключения к приёмке</span></div><div class="filters"><label class="search-box"><span aria-hidden="true">⌕</span><span class="visually-hidden">Найти лабораторию по теме или тексту</span><input id="module-search" type="search" autocomplete="off" placeholder="Найти тему: UART, DMA, таймер…" value="'+escape(query)+'"></label><fieldset class="filter-options"><legend class="visually-hidden">Фильтр лабораторий</legend>'+[['all','Все'],['core','Основной путь'],['optional','С расширениями']].map(([value,label])=>'<label><input type="radio" name="module-filter" value="'+value+'" '+(filter===value?'checked':'')+'><span>'+label+'</span></label>').join('')+'</fieldset></div><p id="filter-count" class="filter-count" role="status" aria-live="polite"></p><div id="module-grid" class="module-grid"></div></section><section><div class="section-heading"><div><h2>Под рукой</h2><p>Настройка, безопасность и инструменты для осознанной практики.</p></div></div><div class="resource-grid">'+resources.map(d=>'<a class="resource-card" href="'+documentHref(d.path)+'">'+escape(d.title)+'<span aria-hidden="true">↗</span></a>').join('')+'</div></section><div class="honesty-note"><span aria-hidden="true">◌</span><p>Прогресс здесь отмечаете вы сами. Чтение страницы не подтверждает навык, а тесты на компьютере не заменяют проверку на реальной плате. Никакие данные не отправляются; для резервной копии используйте экспорт.</p></div>';
    renderCards(); renderHomeReviews();
    $('#module-search').addEventListener('input',event=>{query=event.target.value;renderCards();});
    document.querySelectorAll('[name=module-filter]').forEach(input=>input.addEventListener('change',()=>{filter=input.value;renderCards();}));
  }
  function renderCards() {
    const terms = query.toLocaleLowerCase('ru').trim().split(/\s+/).filter(Boolean);
    const modules = course.modules.filter(m=> (filter==='all'||filter==='core'&&m.track!=='optional'||filter==='optional'&&hasExtension(m)) && terms.every(term=>[m.id,m.title,m.summary,(m.tags||[]).join(' '),m.searchText].join(' ').toLocaleLowerCase('ru').includes(term)));
    $('#filter-count').textContent = 'Показано '+modules.length+' из '+course.modules.length+' лабораторий'+(filter==='optional'?'. Это дополнения внутри основного маршрута.':'.');
    $('#module-grid').innerHTML = modules.length ? modules.map(m=>'<article class="module-card '+(isComplete(m)?'is-finished':'')+'"><div class="card-top"><span class="module-index">LAB <strong>'+number(m)+'</strong></span><span class="track-tag '+(m.track==='optional'?'optional':'')+'">'+(m.track==='optional'?'По желанию':'Основной маршрут')+'</span></div><h3><a href="'+moduleHref(m)+'">'+escape(m.title)+'</a></h3><p>'+escape(m.summary)+'</p><div class="card-footer"><span>'+escape(m.duration)+(m.optional_hours?' · +'+escape(m.optional_hours)+' ч по желанию':'')+'</span><span><span class="status-dot" aria-hidden="true"></span>'+(isComplete(m)?'Практика отмечена':checkpointCount(m)+' / '+m.checkpoints.length)+'</span><a class="card-arrow" href="'+moduleHref(m)+'" aria-label="Открыть лабораторию '+number(m)+': '+escape(m.title)+'">↗</a></div></article>').join(''):'<div class="empty-results"><h3>Пока ничего не нашлось</h3><p>Попробуйте другое слово или уберите фильтр. Поиск работает и по полному тексту лабораторий.</p><button id="clear-search" class="button button-secondary" type="button">Сбросить поиск</button></div>';
    const clear=$('#clear-search'); if(clear)clear.addEventListener('click',()=>{query='';filter='all';home();$('#module-search').focus();});
  }
  function renderHomeReviews() {
    const due = S.due(state,course,Date.now());
    if (!due.length) {$('#home-reviews').innerHTML='';return;}
    $('#home-reviews').innerHTML='<section class="review-panel"><span class="mini-label">Вернуться и вспомнить</span><h2>Пора закрепить '+due.length+' '+(due.length===1?'лабораторию':'лаборатории')+'</h2><p>Закройте прежний код и подсказки. Воспроизведите ключевой шаг, затем проверьте результат.</p><ul>'+due.map(m=>'<li><a href="'+moduleHref(m)+'">'+number(m)+' · '+escape(m.title)+'</a></li>').join('')+'</ul></section>';
  }
  function contents(doc,route) {
    return '<details class="toc" open><summary>На этой странице</summary><ol>' + doc.headings.filter(h=>h.level>1&&h.level<4).map(h=>'<li class="'+(h.level===3?'toc-sub':'')+'"><a href="#section/'+encodeURI(route)+'/'+encodeURIComponent(h.id)+'">'+escape(h.title)+'</a></li>').join('')+'</ol></details>';
  }
  function moduleView(id) {
    const m=moduleById.get(id); if(!m)return notFound();
    const idx=course.modules.indexOf(m), prev=course.modules[idx-1], next=course.modules[idx+1];
    const pre=(m.prerequisites||[]).map(id=>moduleById.get(id)).filter(Boolean);
    const entry=S.getModule(state,m.id);
    $('#main').innerHTML='<div class="breadcrumbs"><a href="#home">Карта маршрута</a><span aria-hidden="true">/</span><span>Лаборатория '+number(m)+'</span></div><header class="lesson-header"><div class="eyebrow">Лаборатория '+number(m)+' / '+course.modules.length+'</div><h1>'+escape(m.title)+'</h1><p>'+escape(m.summary)+'</p><div class="lesson-meta"><span class="track-tag '+(m.track==='optional'?'optional':'')+'">'+(m.track==='optional'?'По желанию':'Основной маршрут')+'</span><span>Около '+escape(m.duration)+'</span>'+(m.optional_hours?'<span>+ '+escape(m.optional_hours)+' ч по желанию</span>':'')+'<span id="module-completion-status">'+(isComplete(m)?'Отмечено выполненным':checkpointCount(m)+' / '+m.checkpoints.length+' проверок')+'</span></div>'+(pre.length?'<p class="prerequisites">Перед началом:'+pre.map(p=>'<a href="'+moduleHref(p)+'">'+number(p)+' · '+escape(p.title)+'</a>').join('; ')+'</p>':'')+'</header><div class="lesson-layout"><article class="lesson-article"><div class="article-body">'+m.html+'</div></article><aside class="lesson-aside" aria-label="Ориентиры лаборатории"><section class="lesson-summary"><h2>Что должно получиться</h2><p>'+escape(m.gate||m.summary)+'</p></section>'+contents(m,'module/'+m.id)+'<a class="source-link" href="'+encodeURI(m.path)+'" download>Скачать исходный Markdown ↗</a></aside></div><section class="learning-check" aria-labelledby="check-title"><span class="mini-label">Зафиксировать результат</span><h2 id="check-title">Проверьте себя на практике</h2><p>Ставьте отметку только после наблюдаемого результата. Подробные критерии и безопасная ошибка описаны в лаборатории.</p><fieldset class="checkpoint-list"><legend class="visually-hidden">Отметки лаборатории '+number(m)+'</legend>'+m.checkpoints.map(c=>'<label class="checkpoint"><input type="checkbox" data-checkpoint="'+escape(c.id)+'" '+(entry.checks.includes(c.id)?'checked':'')+'><span>'+escape(c.label)+'</span></label>').join('')+'<label class="checkpoint self-test"><input type="checkbox" data-checkpoint="selfTest" '+(entry.selfTest?'checked':'')+'><span><strong>Я могу объяснить результат без ИИ и готового ответа</strong><small>Это ваша самооценка. Сайт не оценивает код и не проверяет плату автоматически.</small></span></label></fieldset><p class="check-note">После всех отметок появится план коротких повторений: через 1, 3, 7 и 21 день. Напоминания видны только здесь, когда вы открываете курс.</p><div id="module-review"></div></section><details class="ai-hint"><summary>Как использовать ИИ в этой лаборатории</summary><p>Сначала сформулируйте своё ожидание и проведите один эксперимент. Затем попросите объяснить наблюдение, предложить проверяемую гипотезу или проверить ваше рассуждение. Финальную самопроверку выполните без подсказки.</p>'+(docByPath.has('docs/AI_WORKFLOW.md')?'<p><a href="'+documentHref('docs/AI_WORKFLOW.md')+'">Сценарии работы с ИИ и шаблоны запросов →</a></p>':'')+'</details><nav class="lesson-pagination" aria-label="Соседние лаборатории">'+(prev?'<a href="'+moduleHref(prev)+'"><span>← Предыдущая · '+number(prev)+'</span>'+escape(prev.title)+'</a>':'<a href="#home"><span>← К началу</span>Карта маршрута</a>')+(next?'<a href="'+moduleHref(next)+'"><span>Следующая · '+number(next)+' →</span>'+escape(next.title)+'</a>':'<a href="#home"><span>К практике →</span>Маршрут и повторения</a>')+'</nav>';
    document.querySelectorAll('[data-checkpoint]').forEach(input=>input.addEventListener('change',()=>{
      const was=isComplete(m);
      state=S.change(state,m,input.dataset.checkpoint,input.checked,Date.now());
      const persisted=save();
      refreshNavigation(); renderReview(m);
      $('#module-completion-status').textContent=isComplete(m)?'Отмечено выполненным':checkpointCount(m)+' / '+m.checkpoints.length+' проверок';
      if(!was&&isComplete(m)) notify('Практика отмечена. Первое повторение: '+date(S.getModule(state,m.id).review.dueAt)+'.');
      else if(was&&!isComplete(m)) notify('Отметка завершения и план повторений сняты.');
      else notify(persisted?'Отметка сохранена в этом браузере.':'Отметка изменена. Не забудьте экспортировать прогресс.');
    }));
    renderReview(m);
  }
  function renderReview(m) {
    const target=$('#module-review'); if(!target)return;
    const e=S.getModule(state,m.id); if(!e.review){target.innerHTML='';return;}
    const r=e.review, ready=r.dueAt&&Date.parse(r.dueAt)<=Date.now(), finished=r.step===4;
    target.innerHTML='<div class="module-review"><h3>'+(finished?'Четыре повторения отмечены':ready?'Пора вспомнить без подсказки':'Следующее повторение: '+date(r.dueAt))+'</h3><p>'+(finished?'Вернитесь к задаче снова, если объяснение или перенос пока даются неуверенно.':ready?'Закройте исходный код, ответьте на вопросы и воспроизведите ключевой фрагмент. Отмечайте только реально выполненное повторение.':'Повторение '+(r.step+1)+' из 4. До этой даты отметка недоступна; практиковаться можно в любое время.')+'</p><ul>'+(m.review_prompts||[]).map(p=>'<li>'+escape(p)+'</li>').join('')+'</ul>'+(finished?'':'<button id="mark-review" class="button '+(ready?'button-primary':'button-secondary')+'" type="button" '+(ready?'':'disabled')+'>Повторил без подсказки</button>')+(r.history.length?'<details class="review-history"><summary>История повторений</summary><ul>'+r.history.map((h,i)=>'<li>'+ (i+1)+'. План: '+date(h.plannedAt)+'; выполнено: '+date(h.performedAt)+'.</li>').join('')+'</ul></details>':'')+'</div>';
    const button=$('#mark-review'); if(button)button.addEventListener('click',()=>{
      if(!window.confirm('Вы действительно повторили ключевой шаг и ответили на вопросы без подсказки?'))return;
      state=S.review(state,m,Date.now()); save(); renderReview(m);
      notify('Повторение отмечено. '+(S.getModule(state,m.id).review.dueAt?'Следующее: '+date(S.getModule(state,m.id).review.dueAt)+'.':'План из четырёх повторений завершён.'));
    });
  }
  function documentView(path) {
    const doc=docByPath.get(path);if(!doc)return notFound();
    $('#main').innerHTML='<div class="breadcrumbs"><a href="#home">Карта маршрута</a><span aria-hidden="true">/</span><span>Материалы</span></div><header class="lesson-header"><div class="eyebrow">Под рукой</div><h1>'+escape(doc.title)+'</h1></header><div class="document-layout"><article class="lesson-article"><div class="article-body">'+doc.html+'</div></article><aside class="lesson-aside" aria-label="Навигация по материалу">'+contents(doc,'document/'+doc.path)+'<a class="source-link" href="'+encodeURI(doc.path)+'" download>Скачать исходный Markdown ↗</a></aside></div>';
  }
  function notFound() {
    $('#main').innerHTML='<section class="empty-results"><h1>Такой страницы нет</h1><p>Ссылка может относиться к другой версии курса. Все доступные материалы есть на карте маршрута.</p><a class="button button-primary" href="#home">Вернуться к маршруту</a></section>';
  }
  function closeMenu(){$('#sidebar').classList.remove('is-open');$('#menu-toggle').setAttribute('aria-expanded','false');$('#menu-toggle').setAttribute('aria-label','Открыть навигацию');}
  function route(focus) {
    let value;try{value=decodeURIComponent(location.hash.slice(1));}catch(_){value='invalid';}
    let anchor;
    if(value==='route'){value='home';anchor='route';}
    if(value==='main'){$('#main').focus();return;}
    if(value.startsWith('section/')){const bits=value.slice(8).split('/');anchor='article-'+bits.pop();value=bits.join('/');}
    current=value.startsWith('module/')?{type:'module',id:value.slice(7)}:value.startsWith('document/')?{type:'document',path:value.slice(9)}:!value||value==='home'?{type:'home'}:{type:'missing'};
    if(current.type==='module')moduleView(current.id);else if(current.type==='document')documentView(current.path);else if(current.type==='home')home();else notFound();
    refreshNavigation();closeMenu();
    const title=current.type==='module'?moduleById.get(current.id)?.title:current.type==='document'?docByPath.get(current.path)?.title:'От blink к своему устройству';
    document.title=(title||'Страница не найдена')+' · STM32-практикум';
    if(focus)$('#main').focus({preventScroll:true});
    requestAnimationFrame(()=>{const node=anchor&&document.getElementById(anchor);if(node){for(let parent=node.parentElement;parent;parent=parent.parentElement){if(parent.tagName==='DETAILS')parent.open=true;}const target=node.classList.contains('anchor-target')&&node.nextElementSibling?node.nextElementSibling:node;if(target.getClientRects().length){target.setAttribute('tabindex','-1');if(focus)target.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:'auto'});}else window.scrollTo({top:0,behavior:'auto'});}else window.scrollTo({top:0,behavior:'auto'});});
  }
  async function copyCode(button) {
    const code=button.closest('.code-block').querySelector('code');
    let success=false;
    if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(code.textContent);success=true;}catch(_){/* Try the local-file fallback. */}}
    if(!success){
      const area=document.createElement('textarea');area.value=code.textContent;area.setAttribute('readonly','');area.style.cssText='position:fixed;left:-9999px;top:0';document.body.append(area);area.select();
      try{success=document.execCommand('copy');}catch(_){success=false;}area.remove();button.focus({preventScroll:true});
    }
    if(success){button.textContent='Скопировано';notify('Код скопирован. Проверьте его настройки перед запуском.');setTimeout(()=>{if(button.isConnected)button.textContent='Копировать';},2500);}
    else{const range=document.createRange();range.selectNodeContents(code);const sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);notify('Браузер запретил копирование. Код выделен: нажмите Ctrl+C или ⌘C.');}
  }
  function downloadJSON(text,filename) {
    const blob=new Blob([text],{type:'application/json;charset=utf-8'});
    const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function exportProgress() {
    const data={...state,exportedAt:new Date().toISOString()};
    downloadJSON(JSON.stringify(data,null,2),'stm32-progress-'+new Date().toISOString().slice(0,10)+'.json');notify('Файл экспорта подготовлен. Сохраните его в надёжном месте.');
  }
  async function importProgress(file) {
    const status=$('#import-status');status.classList.remove('error');status.textContent='';
    if(!file)return;
    try{
      if(file.size>S.MAX_BYTES)throw new Error('Файл слишком большой. Максимум 1 МБ.');
      const parsed=S.validate(await file.text(),course);
      const stats=S.stats(parsed,course);
      if(!window.confirm('Заменить текущий прогресс данными из файла? В файле: '+stats.finished+' из '+stats.core+' модулей и '+stats.checked+' отметок. Это заменит текущие отметки и даты повторений.')){status.textContent='Импорт отменён. Прогресс не изменён.';return;}
      state=parsed;storageBlocked=false;const persisted=save();route(false);status.textContent='Импорт выполнен.'+(persisted?'':' Не удалось сохранить в браузере: данные доступны до закрытия страницы.');notify('Прогресс восстановлен из файла.');
    }catch(error){status.classList.add('error');status.textContent=error.message||'Не удалось импортировать файл. Прогресс не изменён.';}
    finally{$('#import-file').value='';}
  }
  load();theme();
  $('#build-id').textContent=' · '+course.build;
  document.addEventListener('click',event=>{
    const copy=event.target.closest('.copy-code');if(copy){copyCode(copy);return;}
    const scroll=event.target.closest('[data-scroll]');if(scroll){event.preventDefault();document.getElementById(scroll.dataset.scroll)?.scrollIntoView({block:'start'});return;}
    const skip=event.target.closest('.skip-link');if(skip){event.preventDefault();$('#main').focus();return;}
    const link=event.target.closest('a[href^="#"]');if(link&&link.getAttribute('href')===location.hash){event.preventDefault();route(true);}
  });
  $('#menu-toggle').addEventListener('click',()=>{const open=!$('#sidebar').classList.contains('is-open');$('#sidebar').classList.toggle('is-open',open);$('#menu-toggle').setAttribute('aria-expanded',String(open));$('#menu-toggle').setAttribute('aria-label',open?'Закрыть навигацию':'Открыть навигацию');});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('#sidebar').classList.contains('is-open')){closeMenu();$('#menu-toggle').focus();}});
  $('.theme-toggle').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark',true));
  document.querySelectorAll('.progress-open').forEach(button=>button.addEventListener('click',()=>{$('#progress-dialog').showModal();}));
  $('.dialog-close').addEventListener('click',()=>$('#progress-dialog').close());
  $('#export-progress').addEventListener('click',exportProgress);
  $('#recover-progress').addEventListener('click',()=>{if(recoveryRaw!==null){downloadJSON(recoveryRaw,'stm32-progress-recovery-'+new Date().toISOString().slice(0,10)+'.json');$('#import-status').textContent='Подготовлена копия исходных несовместимых данных. Эта версия сайта пока не может их импортировать. Текущие временные отметки сохраняются отдельно кнопкой «Экспорт JSON». ';}});
  $('#choose-import').addEventListener('click',()=>$('#import-file').click());
  $('#import-file').addEventListener('change',()=>importProgress($('#import-file').files[0]));
  $('#reset-progress').addEventListener('click',()=>{
    if(!window.confirm('Удалить все отметки и даты повторений этого курса? Отменить сброс нельзя. Сначала сохраните копию. Если версия несовместима, используйте «Скачать исходные данные».'))return;
    state=S.blank(course);storageBlocked=false;const persisted=save();route(false);$('#import-status').classList.remove('error');$('#import-status').textContent=persisted?'Отметки и даты повторений сброшены.':'Отметки сброшены на этой странице. Изменение не сохранено в браузере; при повторном открытии могут вернуться прежние данные.';notify(persisted?'Прогресс сброшен.':'Отметки сброшены только на текущей странице.');
  });
  window.addEventListener('hashchange',()=>route(true));
  window.addEventListener('storage',event=>{
    if(event.key!==STORAGE_KEY)return;
    try{state=event.newValue===null?S.blank(course):S.validate(event.newValue,course);storageBlocked=false;recoveryRaw=null;warn('');const y=window.scrollY;route(false);requestAnimationFrame(()=>window.scrollTo(0,y));notify('Прогресс обновлён из другой вкладки.');}
    catch(_){storageBlocked=true;recoveryRaw=event.newValue;warn('Другая вкладка записала несовместимый прогресс. Сохранение приостановлено: импортируйте совместимый файл или подтвердите сброс.');}
  });
  route(false);
}());
