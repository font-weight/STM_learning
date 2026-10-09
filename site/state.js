/* Pure, dependency-free progress model. Browser and Node compatible. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CourseState = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const VERSION = 1;
  const FORMAT = 'stm32-practice-progress';
  const DAY = 86400000;
  const INTERVALS = [1, 2, 4, 14]; // Reviews on days 1, 3, 7, 21; late reviews retain the intended gap.
  const MAX_BYTES = 1024 * 1024;
  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const iso = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
  function blank(course) { return {format: FORMAT, version: VERSION, courseId: course.id, modules: {}}; }
  function emptyModule() { return {checks: [], selfTest: false, completedAt: null, review: null}; }
  function getModule(state, id) { return own(state.modules, id) ? state.modules[id] : emptyModule(); }
  function complete(entry, module) { return module.checkpoints.length > 0 && module.checkpoints.every(item => entry.checks.includes(item.id)) && entry.selfTest; }
  function validate(input, course) {
    if (typeof input === 'string') {
      if (input.length > MAX_BYTES) throw new Error('Файл слишком большой. Максимум 1 МБ.');
      try { input = JSON.parse(input); } catch (_) { throw new Error('Не удалось прочитать JSON. Выберите файл экспорта прогресса.'); }
    }
    if (!plain(input) || input.format !== FORMAT) throw new Error('Это не файл прогресса STM32-практикума.');
    if (input.version !== VERSION) throw new Error('Эта версия файла не поддерживается. Исходный прогресс не изменён.');
    if (input.courseId !== course.id) throw new Error('Файл относится к другому курсу. Прогресс не изменён.');
    if (!plain(input.modules)) throw new Error('В файле нет корректного списка модулей.');
    const modules = new Map(course.modules.map(m => [m.id, m]));
    const clean = blank(course);
    for (const [id, entry] of Object.entries(input.modules)) {
      const m = modules.get(id);
      if (!m) throw new Error('В файле найден неизвестный модуль. Проверьте версию курса.');
      if (!plain(entry) || !Array.isArray(entry.checks) || typeof entry.selfTest !== 'boolean') throw new Error('Повреждены отметки модуля ' + id + '.');
      const keys = new Set(m.checkpoints.map(c => c.id));
      if (entry.checks.some(c => typeof c !== 'string' || !keys.has(c)) || new Set(entry.checks).size !== entry.checks.length) throw new Error('Неизвестная или повторная отметка в ' + id + '.');
      if (entry.completedAt !== null && !iso(entry.completedAt)) throw new Error('Некорректная дата завершения ' + id + '.');
      const finished = complete(entry, m);
      if (finished !== Boolean(entry.completedAt)) throw new Error('Отметки завершения противоречат друг другу в ' + id + '.');
      let review = null;
      if (entry.review !== null) {
        const r = entry.review;
        if (!plain(r) || !finished || !Number.isInteger(r.step) || r.step < 0 || r.step > INTERVALS.length) throw new Error('Некорректный план повторения ' + id + '.');
        if (r.step < INTERVALS.length ? !iso(r.dueAt) : r.dueAt !== null) throw new Error('Некорректная дата повторения ' + id + '.');
        if (r.lastAt !== null && !iso(r.lastAt)) throw new Error('Некорректная дата последнего повторения ' + id + '.');
        if ((r.step === 0 && r.lastAt !== null) || (r.step > 0 && r.lastAt === null)) throw new Error('Неполная история повторения ' + id + '.');
        if (!Array.isArray(r.history) || r.history.length !== r.step || r.history.some(h => !plain(h) || !iso(h.plannedAt) || !iso(h.performedAt))) throw new Error('Некорректная история повторений ' + id + '.');
        review = {step: r.step, dueAt: r.dueAt, lastAt: r.lastAt, history: r.history.map(h => ({plannedAt: h.plannedAt, performedAt: h.performedAt}))};
      } else if (finished) { throw new Error('В завершённом модуле отсутствует план повторения ' + id + '.'); }
      clean.modules[id] = {checks: [...entry.checks], selfTest: entry.selfTest, completedAt: entry.completedAt, review};
    }
    return clean;
  }
  function change(state, module, field, value, now) {
    const result = JSON.parse(JSON.stringify(state));
    const entry = getModule(result, module.id);
    if (field === 'selfTest') entry.selfTest = Boolean(value);
    else {
      if (!module.checkpoints.some(c => c.id === field)) throw new Error('Unknown checkpoint');
      entry.checks = value ? [...new Set([...entry.checks, field])] : entry.checks.filter(c => c !== field);
    }
    if (complete(entry, module)) {
      if (!entry.completedAt) {
        entry.completedAt = new Date(now).toISOString();
        entry.review = {step: 0, dueAt: new Date(now + DAY).toISOString(), lastAt: null, history: []};
      }
    } else { entry.completedAt = null; entry.review = null; }
    result.modules[module.id] = entry;
    return result;
  }
  function review(state, module, now) {
    const result = JSON.parse(JSON.stringify(state));
    const entry = getModule(result, module.id);
    if (!complete(entry, module) || !entry.review || entry.review.step >= INTERVALS.length) return result;
    if (Date.parse(entry.review.dueAt) > now) return result;
    entry.review.history.push({plannedAt: entry.review.dueAt, performedAt: new Date(now).toISOString()});
    entry.review.step += 1;
    entry.review.lastAt = new Date(now).toISOString();
    entry.review.dueAt = entry.review.step === INTERVALS.length ? null : new Date(now + INTERVALS[entry.review.step] * DAY).toISOString();
    result.modules[module.id] = entry;
    return result;
  }
  function stats(state, course) {
    const core = course.modules.filter(m => m.track !== 'optional');
    const finished = core.filter(m => complete(getModule(state, m.id), m)).length;
    const checked = course.modules.reduce((n, m) => n + getModule(state, m.id).checks.length, 0);
    const total = course.modules.reduce((n, m) => n + m.checkpoints.length, 0);
    return {finished, core: core.length, checked, total, percent: core.length ? Math.round(100 * finished / core.length) : 0};
  }
  function due(state, course, now) {
    return course.modules.filter(m => { const e = getModule(state, m.id); return e.review && e.review.dueAt && Date.parse(e.review.dueAt) <= now; });
  }
  return {VERSION, FORMAT, DAY, INTERVALS, MAX_BYTES, blank, emptyModule, getModule, complete, validate, change, review, stats, due};
}));
