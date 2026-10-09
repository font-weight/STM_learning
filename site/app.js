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
  let storageAvailable = false;
  let recoveryRaw = null;
  let storageMessage = '';
  let current = {type:'home'};
  let navigationVersion = 0;
  let renderedHash = null;
  let toastTimer;
  let filter = 'all', query = '';
  const number = m => String(m.number).padStart(2,'0');
  const moduleHref = m => '#module/' + encodeURIComponent(m.id);
  const documentHref = path => '#document/' + encodeURI(path);
  const hasExtension = m => m.track === 'optional' || Number(m.optional_hours || 0) > 0;
  const date = value => new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value));
  const isComplete = m => S.complete(S.getModule(state,m.id),m);
  const checkpointCount = m => S.getModule(state,m.id).checks.length;

  function storageStatus() {
    const status = $('#storage-status');
    if (!status) return;
    status.textContent = storageBlocked ? 'Сохранение приостановлено: исходные данные защищены.' : storageAvailable ? 'Сохранение в этом браузере доступно.' : 'Отметки временные. Сохраните JSON перед закрытием страницы.';
    status.dataset.state = storageAvailable && !storageBlocked ? 'saved' : 'temporary';
  }
  function warn(text) {
    storageMessage = text;
    const box = $('#storage-warning');
    box.textContent = text;
    box.hidden = !text;
    $('#dialog-storage-warning').textContent=text;
    $('#dialog-storage-warning').hidden=!text;
    $('#recover-progress').hidden=recoveryRaw===null;
    storageStatus();
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
      storageAvailable = true;
      storageStatus();
    } catch (_) {
      warn('Браузер не разрешает сохранять прогресс здесь. Отметки работают до закрытия страницы. Используйте «Мой прогресс → Экспорт JSON» для сохранения.');
    }
  }
  function save() {
    if (storageBlocked) return false;
    try {
      localStorage.setItem(STORAGE_KEY,JSON.stringify(state));
      storageAvailable = true;
      recoveryRaw=null;
      $('#recover-progress').hidden=true;
      if (storageMessage) warn('');
      storageStatus();
      return true;
    } catch (_) {
      storageAvailable = false;
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
    $('#dialog-theme-toggle').textContent=value==='dark'?'Тема: тёмная':'Тема: светлая';
    $('#dialog-theme-toggle').setAttribute('aria-pressed',String(value==='dark'));
    $('#dialog-theme-toggle').setAttribute('aria-label',value==='dark'?'Включить светлую тему':'Включить тёмную тему');
    if (persist) { try {localStorage.setItem(THEME_KEY,value);} catch (_) {notify('Тема изменена только для текущей страницы.');} }
  }
  function refreshNavigation() {
    $('#module-nav').innerHTML = course.modules.map(m => '<li class="' + (isComplete(m)?'done':'') + '"><a href="' + moduleHref(m) + '"' + (current.type==='module'&&current.id===m.id?' aria-current="page"':'') + '><span class="nav-number" aria-hidden="true">' + (isComplete(m)?'✓':number(m)) + '</span><span><span class="visually-hidden">Лаборатория ' + number(m) + '. ' + (isComplete(m)?'Отмечена выполненной. ':'') + '</span>' + escape(m.title) + (m.track==='optional'?'<span class="nav-optional">По желанию</span>':'') + '</span></a></li>').join('');
    $('#resource-nav').innerHTML = course.documents.filter(d=>d.path!=='README.md'&&!d.linked_only).map(d=>'<a href="' + documentHref(d.path) + '"' + (current.type==='document'&&current.path===d.path?' aria-current="page"':'') + '>' + escape(d.title) + '</a>').join('');
    $('.overview-link').setAttribute('aria-current',current.type==='home'?'page':'false');
    const stats = S.stats(state,course);
    $('#sidebar-count').textContent = stats.finished+' / '+stats.core;
    $('#sidebar-progress').max = stats.core;
    $('#sidebar-progress').value = stats.finished;
    $('#dialog-stats').textContent = stats.finished+' из '+stats.core+' лабораторий основного маршрута отмечены выполненными. Отметок практики: '+stats.checked+' / '+stats.total+'. Это самоотчёт, а не оценка навыка.';
  }
  function learningSummary(next) {
    const stats = S.stats(state,course);
    const due = S.due(state,course,Date.now()).length;
    return '<aside class="learning-summary" aria-labelledby="learning-summary-title"><span class="mini-label">Ваши отметки · этот браузер</span><h2 id="learning-summary-title">Основной маршрут</h2><div class="learning-count"><strong>'+stats.finished+'</strong><span>из '+stats.core+' лабораторий<br>отмечено выполненными</span></div><progress value="'+stats.finished+'" max="'+stats.core+'" aria-label="Лабораторий основного маршрута отмечено выполненными"></progress><p class="learning-evidence">Отметки — ваш самоотчёт. Подтверждайте результат измерением на плате.</p><div class="learning-next"><span>'+(stats.finished===stats.core?'Вернуться к практике':'Следующая лаборатория')+'</span><a href="'+moduleHref(next)+'">'+number(next)+' · '+escape(next.title)+'</a></div>'+(due?'<a class="learning-reviews" href="#home-reviews" data-scroll="home-reviews">К повторению сегодня: '+due+'</a>':'')+'</aside>';
  }
  function home() {
    const next = course.modules.find(m=>m.track!=='optional'&&!isComplete(m)) || course.modules[0];
    const started = Object.keys(state.modules).some(id=>state.modules[id].checks.length>0 || state.modules[id].selfTest);
    const allDone = S.stats(state,course).finished === S.stats(state,course).core;
    const extra = Number(course.optional_extension_hours||0)+Number(course.optional_module_hours||0);
    const firstLink = docByPath.has('docs/START_HERE.md') ? documentHref('docs/START_HERE.md') : moduleHref(course.modules[0]);
    const resources = course.documents.filter(d=>d.path!=='README.md'&&!d.linked_only);
    $('#main').innerHTML = '<section class="hero"><div><div class="eyebrow">Практический маршрут · для Arduino / AVR</div><h1>От первого blink<br>к <span>своему устройству.</span></h1><p class="hero-lead">Освойте STM32F103 руками: отладчик, периферия и измерения. В финале соберите собственный измеритель с консолью и журналом данных.</p><div class="hero-buttons"><a class="button button-primary" href="' + (started?moduleHref(next):firstLink) + '">' + (allDone?'Вернуться к практике':started?'Продолжить · '+number(next):'Начать с настройки') + '</a><a class="button button-secondary" href="#route" data-scroll="route">Посмотреть маршрут</a></div><div class="hero-meta"><span><strong>' + course.modules.length + '</strong> лабораторий</span><span><strong>≈ '+escape(course.core_hours||'48')+' ч</strong> основы</span><span><strong>60–90 мин</strong> на сессию</span></div></div>' + learningSummary(next) + '</section><section class="start-strip"><div><span class="mini-label">Первый шаг · лаборатория 00</span><h2>Сначала докажите, что управляете платой.</h2><p>Проверьте питание и SWD, соберите проект, прошейте Blue Pill и остановите его в отладчике. Затем переходите к периферии.</p></div><a class="button button-secondary" href="'+moduleHref(course.modules[0])+'">Открыть лабораторию 00</a></section><div class="practice-loop" aria-label="Как устроена практика"><div class="loop-item"><span class="loop-number">01 / СДЕЛАТЬ</span><h3>Собрать и измерить</h3><p>Получите наблюдаемый результат на своей плате.</p></div><div class="loop-item"><span class="loop-number">02 / РАЗОБРАТЬСЯ</span><h3>Найти причину ошибки</h3><p>Безопасно измените один параметр. Объясните, что произошло.</p></div><div class="loop-item"><span class="loop-number">03 / ЗАКРЕПИТЬ</span><h3>Повторить без подсказки</h3><p>Восстановите ключевой шаг и перенесите навык в новую задачу.</p></div></div><div id="home-reviews"></div><section id="route"><div class="section-heading"><div><h2>Ваш маршрут</h2><p>Идите по порядку или вернитесь к нужному навыку.' + (extra?' Расширения добавят до '+extra+' ч.':'') + '</p></div><span class="section-caption">От подключения к приёмке</span></div><div class="filters"><label class="search-box"><span aria-hidden="true">⌕</span><span class="visually-hidden">Найти лабораторию по теме или тексту</span><input id="module-search" type="search" autocomplete="off" placeholder="Найти тему: UART, DMA, таймер…" value="'+escape(query)+'"></label><fieldset class="filter-options"><legend class="visually-hidden">Фильтр лабораторий</legend>'+[['all','Все'],['core','Основной путь'],['optional','С расширениями']].map(([value,label])=>'<label><input type="radio" name="module-filter" value="'+value+'" '+(filter===value?'checked':'')+'><span>'+label+'</span></label>').join('')+'</fieldset></div><p id="filter-count" class="filter-count" role="status" aria-live="polite"></p><div id="module-grid" class="module-grid"></div></section><section><div class="section-heading"><div><h2>Под рукой</h2><p>Настройка, безопасность и инструменты для осознанной практики.</p></div></div><div class="resource-grid">'+resources.map(d=>'<a class="resource-card" href="'+documentHref(d.path)+'">'+escape(d.title)+'</a>').join('')+'</div></section><div class="honesty-note"><span aria-hidden="true">◌</span><p>Прогресс здесь отмечаете вы сами. Чтение страницы не подтверждает навык, а тесты на компьютере не заменяют проверку на реальной плате. Прогресс хранится в этом браузере; для резервной копии используйте экспорт.</p></div>';
    renderCards(); renderHomeReviews();
    $('#module-search').addEventListener('input',event=>{query=event.target.value;renderCards();});
    document.querySelectorAll('[name=module-filter]').forEach(input=>input.addEventListener('change',()=>{filter=input.value;renderCards();}));
  }
  function renderCards() {
    const terms = query.toLocaleLowerCase('ru').trim().split(/\s+/).filter(Boolean);
    const modules = course.modules.filter(m=> (filter==='all'||filter==='core'&&m.track!=='optional'||filter==='optional'&&hasExtension(m)) && terms.every(term=>[m.id,m.title,m.summary,(m.tags||[]).join(' '),m.searchText].join(' ').toLocaleLowerCase('ru').includes(term)));
    $('#filter-count').textContent = 'Показано '+modules.length+' из '+course.modules.length+' лабораторий'+(filter==='optional'?'. Это дополнения внутри основного маршрута.':'.');
    $('#module-grid').innerHTML = modules.length ? modules.map(m=>'<article class="module-card '+(isComplete(m)?'is-finished':'')+'"><div class="card-top"><span class="module-index">LAB <strong>'+number(m)+'</strong></span><span class="track-tag '+(m.track==='optional'?'optional':'')+'">'+(m.track==='optional'?'По желанию':'Основной маршрут')+'</span></div><h3><a href="'+moduleHref(m)+'">'+escape(m.title)+'</a></h3><p>'+escape(m.summary)+'</p><div class="card-footer"><span>'+escape(m.duration)+(m.optional_hours?' · +'+escape(m.optional_hours)+' ч по желанию':'')+'</span><span><span class="status-dot" aria-hidden="true"></span>'+(isComplete(m)?'Практика отмечена':checkpointCount(m)+' / '+m.checkpoints.length)+'</span><a class="card-open" href="'+moduleHref(m)+'" aria-label="Открыть лабораторию '+number(m)+': '+escape(m.title)+'">Открыть</a></div></article>').join(''):'<div class="empty-results"><h3>Пока ничего не нашлось</h3><p>Попробуйте другое слово или уберите фильтр. Поиск работает и по полному тексту лабораторий.</p><button id="clear-search" class="button button-secondary" type="button">Сбросить поиск</button></div>';
    const clear=$('#clear-search'); if(clear)clear.addEventListener('click',()=>{query='';filter='all';home();$('#module-search').focus();});
  }
  function renderHomeReviews() {
    const due = S.due(state,course,Date.now());
    if (!due.length) {$('#home-reviews').innerHTML='';return;}
    $('#home-reviews').innerHTML='<section class="review-panel"><span class="mini-label">Вернуться и вспомнить</span><h2>Пора вернуться к практике: '+due.length+' '+(due.length===1?'лаборатория':due.length<5?'лаборатории':'лабораторий')+'</h2><p>Закройте прежний код и подсказки. Воспроизведите ключевой шаг, затем проверьте результат.</p><ul>'+due.map(m=>'<li><a href="#recall/'+encodeURIComponent(m.id)+'">'+number(m)+' · '+escape(m.title)+'</a></li>').join('')+'</ul></section>';
  }
  function contents(doc,route) {
    return '<details class="toc"'+(matchMedia('(min-width: 1251px)').matches?' open':'')+'><summary>На этой странице</summary><ol>' + doc.headings.filter(h=>h.level>1&&h.level<4).map(h=>'<li class="'+(h.level===3?'toc-sub':'')+'"><a href="#section/'+encodeURI(route)+'/'+encodeURIComponent(h.id)+'">'+escape(h.title)+'</a></li>').join('')+'</ol></details>';
  }
  function moduleView(id, recall = false) {
    const m = moduleById.get(id); if (!m) return notFound();
    const idx = course.modules.indexOf(m), prev = course.modules[idx - 1], next = course.modules[idx + 1];
    const pre = (m.prerequisites || []).map(id => moduleById.get(id)).filter(Boolean);
    const entry = S.getModule(state, m.id);
    const prompts = m.review_prompts && m.review_prompts.length ? m.review_prompts : [
      'Какой результат вы ожидали и чем подтвердили его на своей плате?',
      'Как отличить выбранную причину неисправности от другой правдоподобной причины?',
      'Как изменить решение для похожей задачи без готового образца?'
    ];
    const hidden = recall ? ' hidden' : '';
    $('#main').innerHTML = `
      <div class="breadcrumbs"><a href="#home">Карта маршрута</a><span aria-hidden="true">/</span><span>Лаборатория ${number(m)}</span></div>
      <header class="lesson-header">
        <div class="eyebrow">Лаборатория ${number(m)} · STM32F103</div>
        <h1>${escape(m.title)}</h1><p>${escape(m.summary)}</p>
        <div class="lesson-meta"><span class="track-tag ${m.track === 'optional' ? 'optional' : ''}">${m.track === 'optional' ? 'По желанию' : 'Основной маршрут'}</span>
          <span>Около ${escape(m.duration)}</span>${m.optional_hours ? '<span>+ ' + escape(m.optional_hours) + ' ч по желанию</span>' : ''}
          <span id="module-completion-status">${isComplete(m) ? 'Практика отмечена' : checkpointCount(m) + ' / ' + m.checkpoints.length + ' отметок практики'}</span>
        </div>
        ${pre.length ? '<p class="prerequisites">Перед началом: ' + pre.map(p => '<a href="' + moduleHref(p) + '">' + number(p) + ' · ' + escape(p.title) + '</a>').join('; ') + '</p>' : ''}
      </header>
      <nav class="lesson-actions" aria-label="Режим лаборатории">
        <a href="${moduleHref(m)}"${!recall ? ' aria-current="page"' : ''}>Материал</a>
        <a href="#recall/${encodeURIComponent(m.id)}"${recall ? ' aria-current="page"' : ''}>Без подсказок</a>
        <a href="#section/module/${encodeURIComponent(m.id)}/reader-checks">Зафиксировать результат </a>
      </nav>
      <section id="recall-panel" class="recall-panel" aria-labelledby="recall-title"${recall ? '' : ' hidden'}>
        <span class="mini-label">Самостоятельная попытка</span>
        <h2 id="recall-title" tabindex="-1">Сначала своя версия</h2>
        <p>Материал и подсказки сейчас скрыты. Закройте прежний код и записи. Ответьте вслух или в своём журнале; где уместно, восстановите ключевой фрагмент с чистого листа.</p>
        <ol class="recall-prompts">${prompts.map(prompt => '<li>' + escape(prompt) + '</li>').join('')}</ol>
        <div class="recall-compare"><h3>Перед сверкой</h3><p>Назовите наблюдение, которое подтвердит ваш ответ. Если застряли, запишите, что именно пока не можете объяснить. Затем откройте материал, проверьте свою версию и повторите слабое место.</p></div>
        <a class="button button-primary" href="${moduleHref(m)}">Сверить с материалом</a>
        <p class="recall-note">Этот режим не выставляет оценку и не меняет прогресс. Отметку ставьте после собственной проверки результата.</p>
      </section>
      <div class="lesson-layout"${hidden}>
        <aside class="lesson-aside" aria-label="Ориентиры лаборатории">
          <section class="lesson-summary"><h2>Что должно получиться</h2><p>${escape(m.gate || m.summary)}</p></section>
          ${contents(m, 'module/' + m.id)}
          <a class="source-link" href="${encodeURI(m.path)}" download>Скачать исходный Markdown</a>
        </aside>
        <article class="lesson-article" aria-label="Материал лаборатории"><div class="article-body">${m.html}</div></article>
      </div>
      <section class="learning-check" id="article-reader-checks" aria-labelledby="check-title"${hidden}>
        <span class="mini-label">Зафиксировать результат</span><h2 id="check-title">Проверьте себя на практике</h2>
        <p>Отмечайте только подтверждённое наблюдением. Подробные критерии и безопасная ошибка описаны в лаборатории. Самостоятельность результата запишите в журнале: самостоятельно, с опорой или нужна доработка.</p>
        <fieldset class="checkpoint-list"><legend class="visually-hidden">Отметки лаборатории ${number(m)}</legend>
          ${m.checkpoints.map(c => '<label class="checkpoint"><input type="checkbox" data-checkpoint="' + escape(c.id) + '" ' + (entry.checks.includes(c.id) ? 'checked' : '') + '><span>' + escape(c.label) + '</span></label>').join('')}
          <label class="checkpoint self-test"><input type="checkbox" data-checkpoint="selfTest" ${entry.selfTest ? 'checked' : ''}><span><strong>Я могу объяснить результат без ИИ и готового ответа</strong><small>Это ваша самооценка. Сайт не оценивает код и не проверяет плату автоматически.</small></span></label>
        </fieldset>
        <p class="check-note">После всех отметок появится план повторений: примерно через 1, 3, 7 и 21 день. Это удобный исходный ритм, а не обязательный срок: при необходимости возвращайтесь раньше. Напоминания видны только при открытом курсе.</p>
        <div id="module-review"></div>
      </section>
      <details class="ai-hint"${hidden}><summary>Как использовать ИИ в этой лаборатории</summary><p>Сначала сформулируйте своё ожидание и проведите один эксперимент. Затем попросите объяснить наблюдение, предложить проверяемую гипотезу или проверить ваше рассуждение. Финальную самопроверку выполните без подсказки.</p>${docByPath.has('docs/AI_WORKFLOW.md') ? '<p><a href="' + documentHref('docs/AI_WORKFLOW.md') + '">Сценарии работы с ИИ и шаблоны запросов</a></p>' : ''}</details>
      <nav class="lesson-pagination" aria-label="Соседние лаборатории">
        ${prev ? '<a href="' + moduleHref(prev) + '"><span>Предыдущая · ' + number(prev) + '</span>' + escape(prev.title) + '</a>' : '<a href="#home"><span>К началу</span>Карта маршрута</a>'}
        ${next ? '<a href="' + moduleHref(next) + '"><span>Следующая · ' + number(next) + '</span>' + escape(next.title) + '</a>' : '<a href="#home"><span>К практике</span>Маршрут и повторения</a>'}
      </nav>`;
    document.querySelectorAll('[data-checkpoint]').forEach(input => input.addEventListener('change', () => {
      const was = isComplete(m);
      state = S.change(state, m, input.dataset.checkpoint, input.checked, Date.now());
      const persisted = save();
      refreshNavigation(); renderReview(m);
      $('#module-completion-status').textContent = isComplete(m) ? 'Практика отмечена' : checkpointCount(m) + ' / ' + m.checkpoints.length + ' отметок практики';
      if (!was && isComplete(m)) notify('Практика отмечена. Первое повторение: ' + date(S.getModule(state, m.id).review.dueAt) + '.');
      else if (was && !isComplete(m)) notify('Отметка завершения и план повторений сняты.');
      else notify(persisted ? 'Отметка сохранена в этом браузере.' : 'Отметка изменена. Не забудьте экспортировать прогресс.');
    }));
    renderReview(m);
  }
  function renderReview(m) {
    const target=$('#module-review'); if(!target)return;
    const e=S.getModule(state,m.id); if(!e.review){target.innerHTML='';return;}
    const r=e.review, ready=r.dueAt&&Date.parse(r.dueAt)<=Date.now(), finished=r.step===4;
    target.innerHTML='<div class="module-review"><h3>'+(finished?'Четыре повторения отмечены':ready?'Пора вспомнить без подсказки':'Следующее повторение: '+date(r.dueAt))+'</h3><p>'+(finished?'Вернитесь к задаче снова, если объяснение или перенос пока даются неуверенно.':ready?'Закройте исходный код, ответьте на вопросы и воспроизведите ключевой фрагмент. Отмечайте только реально выполненное повторение.':'Плановое повторение '+(r.step+1)+' из 4. Отметка откроется в эту дату; режим «Без подсказок» доступен в любое время.')+'</p><p><a href="#recall/'+encodeURIComponent(m.id)+'">Открыть режим без подсказок</a></p><ul>'+(m.review_prompts||[]).map(p=>'<li>'+escape(p)+'</li>').join('')+'</ul>'+(finished?'':'<button id="mark-review" class="button '+(ready?'button-primary':'button-secondary')+'" type="button" '+(ready?'':'disabled')+'>Повторил без подсказки</button>')+(r.history.length?'<details class="review-history"><summary>История повторений</summary><ul>'+r.history.map((h,i)=>'<li>'+ (i+1)+'. План: '+date(h.plannedAt)+'; выполнено: '+date(h.performedAt)+'.</li>').join('')+'</ul></details>':'')+'</div>';
    const button=$('#mark-review'); if(button)button.addEventListener('click',()=>{
      if(!window.confirm('Вы действительно повторили ключевой шаг и ответили на вопросы без подсказки?'))return;
      state=S.review(state,m,Date.now()); save(); renderReview(m);
      notify('Повторение отмечено. '+(S.getModule(state,m.id).review.dueAt?'Следующее: '+date(S.getModule(state,m.id).review.dueAt)+'.':'План из четырёх повторений завершён.'));
    });
  }
  function documentView(path) {
    const doc=docByPath.get(path);if(!doc)return notFound();
    $('#main').innerHTML='<div class="breadcrumbs"><a href="#home">Карта маршрута</a><span aria-hidden="true">/</span><span>Материалы</span></div><header class="lesson-header"><div class="eyebrow">Под рукой</div><h1>'+escape(doc.title)+'</h1></header><div class="document-layout"><aside class="lesson-aside" aria-label="Навигация по материалу">'+contents(doc,'document/'+doc.path)+'<a class="source-link" href="'+encodeURI(doc.path)+'" download>Скачать исходный Markdown</a></aside><article class="lesson-article"><div class="article-body">'+doc.html+'</div></article></div>';
  }
  function notFound() {
    $('#main').innerHTML='<section class="empty-results"><h1>Такой страницы нет</h1><p>Ссылка может относиться к другой версии курса. Все доступные материалы есть на карте маршрута.</p><a class="button button-primary" href="#home">Вернуться к маршруту</a></section>';
  }
  function closeMenu(){$('#sidebar').classList.remove('is-open');$('#menu-toggle').setAttribute('aria-expanded','false');$('#menu-toggle').setAttribute('aria-label','Открыть навигацию');}
  function route(focus) {
    renderedHash = location.hash;
    const version = ++navigationVersion;
    let value;try{value=decodeURIComponent(location.hash.slice(1));}catch(_){value='invalid';}
    let anchor;
    if(value==='route'){value='home';anchor='route';}
    if(value==='main'){$('#main').focus();return;}
    if(value.startsWith('section/')){const bits=value.slice(8).split('/');anchor='article-'+bits.pop();value=bits.join('/');}
    const recall = value.startsWith('recall/');
    if (recall) { value = 'module/' + value.slice(7); anchor = 'recall-title'; }
    current=value.startsWith('module/')?{type:'module',id:value.slice(7)}:value.startsWith('document/')?{type:'document',path:value.slice(9)}:!value||value==='home'?{type:'home'}:{type:'missing'};
    if(current.type==='module')moduleView(current.id, recall);else if(current.type==='document')documentView(current.path);else if(current.type==='home')home();else notFound();
    refreshNavigation();closeMenu();
    const title=current.type==='module'?moduleById.get(current.id)?.title:current.type==='document'?docByPath.get(current.path)?.title:current.type==='home'?'От blink к своему устройству':null;
    document.title=(title?(recall?'Без подсказок · ':'')+title:'Страница не найдена')+' · STM32-практикум';
    if(focus)$('#main').focus({preventScroll:true});
    requestAnimationFrame(()=>{if(version!==navigationVersion)return;const node=anchor&&document.getElementById(anchor);if(node){for(let parent=node.parentElement;parent;parent=parent.parentElement){if(parent.tagName==='DETAILS')parent.open=true;}const target=node.classList.contains('anchor-target')&&node.nextElementSibling?node.nextElementSibling:node;if(target.getClientRects().length){target.setAttribute('tabindex','-1');if(focus)target.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:'auto'});}else window.scrollTo({top:0,behavior:'auto'});}else window.scrollTo({top:0,behavior:'auto'});});
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
  // Optional page-scoped browser interoperability. No AI service or network client.
  // Only the public curriculum and existing navigation are exposed, never progress data.
  let browserToolLifecycle = null;
  function toolInput(input, fields, required = fields) {
    if (!input || typeof input !== 'object' || Array.isArray(input) ||
        Object.keys(input).some(key => !fields.includes(key)) ||
        required.some(key => !Object.prototype.hasOwnProperty.call(input,key))) {
      throw new TypeError('Некорректные параметры инструмента.');
    }
    return input;
  }
  function toolModule(id) {
    if (typeof id !== 'string' || id.length > 128 || !moduleById.has(id)) {
      throw new TypeError('Неизвестная лаборатория.');
    }
    return moduleById.get(id);
  }
  async function openToolRoute(hash, result) {
    location.hash = hash;
    route(true); // The same rendering, focus and navigation action as visible links.
    await new Promise(resolve => requestAnimationFrame(resolve));
    if (location.hash !== hash) throw new Error('Переход отменён: открыта другая страница.');
    return result;
  }
  function registerBrowserTools() {
    if (browserToolLifecycle) return;
    let context;
    try {
      context = document.modelContext;
      if (!context || typeof context.registerTool !== 'function' || typeof AbortController === 'undefined') return;
    } catch (_) { return; }
    const lifecycle = new AbortController();
    browserToolLifecycle = lifecycle;
    const definitions = [
      {
        name:'read_course_curriculum', title:'Прочитать маршрут курса',
        description:'Return public laboratory and resource metadata. Does not read private progress, open pages or mark learning complete.',
        inputSchema:{type:'object',properties:{},additionalProperties:false},
        annotations:{readOnlyHint:true,untrustedContentHint:false},
        execute(input) {
          toolInput(input,[]);
          return {courseId:course.id,modules:course.modules.map(m=>({id:m.id,number:m.number,title:m.title,summary:m.summary,duration:m.duration,track:m.track,prerequisites:[...(m.prerequisites||[])]})),resources:course.documents.filter(d=>d.path!=='README.md'&&!d.linked_only).map(d=>({path:d.path,title:d.title}))};
        }
      },
      {
        name:'navigate_course', title:'Открыть материал курса',
        description:'Open the visible course home, a known laboratory or a known resource. Changes the current page only; never marks learning complete.',
        inputSchema:{type:'object',properties:{view:{type:'string',enum:['home','module','document']},moduleId:{type:'string',maxLength:128},documentPath:{type:'string',maxLength:512}},required:['view'],additionalProperties:false},
        annotations:{readOnlyHint:false,untrustedContentHint:false},
        execute(input) {
          toolInput(input,['view','moduleId','documentPath'],['view']);
          if (input.view === 'home') { toolInput(input,['view']); return openToolRoute('#home',{view:'home'}); }
          if (input.view === 'module') {
            toolInput(input,['view','moduleId']);
            const m = toolModule(input.moduleId);
            return openToolRoute(moduleHref(m),{view:'module',moduleId:m.id,title:m.title});
          }
          if (input.view === 'document') {
            toolInput(input,['view','documentPath']);
            if (typeof input.documentPath !== 'string' || input.documentPath.length > 512 || !docByPath.has(input.documentPath)) throw new TypeError('Неизвестный материал.');
            const doc = docByPath.get(input.documentPath);
            return openToolRoute(documentHref(doc.path),{view:'document',documentPath:doc.path,title:doc.title});
          }
          throw new TypeError('Неизвестный вид страницы.');
        }
      },
      {
        name:'start_course_recall', title:'Начать повторение без подсказок',
        description:'Open the existing recall view for a known laboratory, hiding lesson content. Starts a practice attempt only; never confirms or completes a review.',
        inputSchema:{type:'object',properties:{moduleId:{type:'string',maxLength:128}},required:['moduleId'],additionalProperties:false},
        annotations:{readOnlyHint:false,untrustedContentHint:false},
        execute(input) {
          toolInput(input,['moduleId']);
          const m = toolModule(input.moduleId);
          return openToolRoute('#recall/'+encodeURIComponent(m.id),{view:'recall',moduleId:m.id,title:m.title});
        }
      }
    ];
    for (const definition of definitions) {
      const execute = definition.execute;
      definition.execute = input => {
        if (lifecycle.signal.aborted) throw new Error('Страница уже закрыта.');
        return execute(input);
      };
      // A rejected optional registration must not interrupt the course.
      try { Promise.resolve(context.registerTool(definition,{signal:lifecycle.signal})).catch(()=>{}); }
      catch (_) { /* Unsupported or unavailable registry: the visible reader still works. */ }
    }
  }
  window.addEventListener('pagehide',()=>{if(browserToolLifecycle)browserToolLifecycle.abort();browserToolLifecycle=null;});
  window.addEventListener('pageshow',registerBrowserTools);
  load();theme();
  $('#build-id').textContent=' · '+course.build;
  document.addEventListener('click',event=>{
    const wrap=event.target.closest('.wrap-code');if(wrap){const block=wrap.closest('.code-block');const active=block.classList.toggle('is-wrapped');wrap.setAttribute('aria-pressed',String(active));notify(active?'Перенос длинных строк включён. Исходный код при копировании не меняется.':'Перенос строк выключен. Длинные строки можно прокручивать.');return;}
    const copy=event.target.closest('.copy-code');if(copy){copyCode(copy);return;}
    const scroll=event.target.closest('[data-scroll]');if(scroll){event.preventDefault();document.getElementById(scroll.dataset.scroll)?.scrollIntoView({block:'start'});return;}
    const skip=event.target.closest('.skip-link');if(skip){event.preventDefault();$('#main').focus();return;}
    const link=event.target.closest('a[href^="#"]');if(link&&link.getAttribute('href')===location.hash){event.preventDefault();route(true);}
  });
  $('#menu-toggle').addEventListener('click',()=>{const open=!$('#sidebar').classList.contains('is-open');$('#sidebar').classList.toggle('is-open',open);$('#menu-toggle').setAttribute('aria-expanded',String(open));$('#menu-toggle').setAttribute('aria-label',open?'Закрыть навигацию':'Открыть навигацию');});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('#sidebar').classList.contains('is-open')){closeMenu();$('#menu-toggle').focus();}});
  [$('.theme-toggle'),$('#dialog-theme-toggle')].forEach(button=>button.addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark',true)));
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
  window.addEventListener('hashchange',()=>{if(location.hash!==renderedHash)route(true);});
  window.addEventListener('storage',event=>{
    if(event.key!==STORAGE_KEY)return;
    try{state=event.newValue===null?S.blank(course):S.validate(event.newValue,course);storageBlocked=false;storageAvailable=true;recoveryRaw=null;warn('');const y=window.scrollY;route(false);const version=navigationVersion;requestAnimationFrame(()=>{if(version===navigationVersion)window.scrollTo(0,y);});notify('Прогресс обновлён из другой вкладки.');}
    catch(_){storageBlocked=true;recoveryRaw=event.newValue;warn('Другая вкладка записала несовместимый прогресс. Сохранение приостановлено: импортируйте совместимый файл или подтвердите сброс.');}
  });
  route(false);
  registerBrowserTools();
}());
