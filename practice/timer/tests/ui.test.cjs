"use strict";
// Small dependency-free DOM harness: exercises shipped handlers, not browser layout.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const core = html.match(/<script id="timer-core">([\s\S]*?)<\/script>/)[1];
const ui = html.match(/<script id="timer-ui">([\s\S]*?)<\/script>/)[1];
const elements = new Map();
let focused = null;
for (const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
  const [, tag, attrs, id] = match;
  assert.ok(!elements.has(id), `Duplicate id: ${id}`);
  elements.set(id, {
    tag, id, value: "", hidden: /\bhidden\b/.test(attrs), disabled: /\bdisabled\b/.test(attrs),
    required: /\brequired\b/.test(attrs), textContent: "", handlers: {}, attrs: {},
    addEventListener(type, handler) { this.handlers[type] = handler; },
    setAttribute(key, value) { this.attrs[key] = value; },
    removeAttribute(key) { delete this.attrs[key]; },
    focus() { focused = id; }
  });
}
const labels = new Map([...html.matchAll(/<label for="([^"]+)">([^<]*)<\/label>/g)].map(m => [m[1], { textContent: m[2] }]));
const get = id => { assert.ok(elements.has(id), `Missing id: ${id}`); return elements.get(id); };
get("practice").reset = () => {
  for (const element of elements.values()) if (["input", "select"].includes(element.tag)) element.value = "";
  get("profile").value = "hsi8"; get("timer").value = "TIM2";
};
get("practice").querySelectorAll = selector => {
  assert.equal(selector, '[aria-invalid="true"]');
  return [...elements.values()].filter(element => element.attrs["aria-invalid"] === "true");
};
const document = {
  getElementById: get,
  querySelector(selector) {
    const match = selector.match(/^label\[for="([^"]+)"\]$/);
    assert.ok(match && labels.has(match[1]), `Missing label for ${selector}`); return labels.get(match[1]);
  }
};
vm.runInNewContext(`${core}\n${ui}`, { document, Intl }, { timeout: 1000 });
const input = (id, value) => { get(id).value = value; get(id).handlers.input(); };
const submit = () => get("practice").handlers.submit({ preventDefault() {} });
const predict = (timer="8000000", counter="1000000", state="periodic", update="1000") => {
  input("pred-timer", timer); input("pred-counter", counter); input("pred-state", state);
  if (state === "periodic") input("pred-update", update);
};
let count = 0;
function test(name, run) { run(); count++; console.log(`ok ${count} - ${name}`); }

test("Initial state keeps computed results hidden and requires learner predictions", () => {
  assert.equal(get("result").hidden, true); assert.equal(get("pred-update").disabled, true);
  submit(); assert.equal(get("result").hidden, true); assert.equal(get("error").hidden, false); assert.equal(focused, "psc");
  input("psc", "7"); input("arr", "999"); submit(); assert.equal(focused, "pred-timer"); assert.equal(get("result").hidden, true);
});
test("Complete prediction reveals baseline calculation without a grade or assessment mutation", () => {
  predict(); submit(); assert.equal(get("result").hidden, false); assert.equal(focused, "result-heading");
  assert.match(get("value-update").textContent, /1\s000 Гц/); assert.match(get("comparison-update").textContent, /0%/);
});
test("PWM Hz value is labelled frequency; its period remains separately expressed in seconds", () => {
  assert.match(html, /<dt>f_PWM · частота повторения edge-aligned PWM<\/dt>/);
  assert.doesNotMatch(html, /<dt>f_PWM · период(?:\s|<)/);
  assert.match(get("value-pwm").textContent, /1\s000 Гц/);
  assert.match(get("period-pwm").textContent, /^Период = 0,001 с\./);
});
test("Each description-list metric has dt then dd with value span and explanation inside dd", () => {
  const metrics = html.match(/<dl class="metrics">([\s\S]*?)<\/dl>/);
  assert.ok(metrics, "The description list must remain present.");
  const groups = [...metrics[1].matchAll(/<div class="metric">([\s\S]*?)<\/div>/g)];
  const ids = [["value-timer", "comparison-timer"], ["value-counter", "comparison-counter"], ["value-update", "comparison-update"], ["value-pwm", "period-pwm"]];
  assert.equal(groups.length, ids.length);
  assert.equal(metrics[1].replace(/<div class="metric">[\s\S]*?<\/div>/g, "").trim(), "", "No stray content outside metric groups.");
  groups.forEach((group, index) => {
    const [valueId, explanationId] = ids[index];
    assert.match(group[1], new RegExp(`^<dt>[^<]+</dt><dd><span id="${valueId}"></span><p id="${explanationId}"></p></dd>$`));
    assert.equal(get(valueId).tag, "span", "textContent updates must target only the nested value span.");
    assert.equal(get(explanationId).tag, "p");
  });
});
test("Nested explanation styling stays small and normal weight rather than inheriting the numeric value style", () => {
  const style = html.match(/\.metric dd p\{([^}]+)\}/);
  assert.ok(style); assert.match(style[1], /font-size:14px(?:;|$)/);
  assert.match(style[1], /font-weight:400(?:;|$)/); assert.match(style[1], /line-height:1\.6(?:;|$)/);
});
test("Prediction edit hides old results; new comparison reflects only the new attempt", () => {
  input("pred-update", "900"); assert.equal(get("result").hidden, true); submit();
  assert.match(get("comparison-update").textContent, /-10%/);
});
test("Changing clock profile clears all predictions and requires a new attempt", () => {
  input("profile", "hse72"); assert.equal(get("hse-notice").hidden, false); assert.equal(get("result").hidden, true);
  for (const id of ["pred-timer", "pred-counter", "pred-state", "pred-update"]) assert.equal(get(id).value, "");
  submit(); assert.equal(focused, "pred-timer"); assert.equal(get("result").hidden, true);
});
test("HSE72 TIM2 result makes APB doubling explicit", () => {
  input("psc", "71"); predict("72000000"); submit();
  assert.match(get("clock-chain").textContent, /APB \/2 включает удвоение/);
  assert.match(get("clock-chain").textContent, /× 2/); assert.match(get("value-update").textContent, /1\s000 Гц/);
});
test("Changing TIM2 to TIM1 resets predictions and shows APB2 plus RCR0", () => {
  input("timer", "TIM1"); assert.equal(get("result").hidden, true); predict("72000000"); submit();
  assert.match(get("clock-chain").textContent, /APB2/); assert.match(get("clock-chain").textContent, /удвоения timer clock нет/);
  assert.match(get("register-chain").textContent, /RCR=0/);
});
test("ARR0 prediction disables frequency input and reveals blocked counter, not a false result", () => {
  input("arr", "0"); predict("72000000", "1000000", "blocked");
  assert.equal(get("pred-update").disabled, true); assert.equal(get("pred-update").required, false); submit();
  assert.equal(get("zero-notice").hidden, false); assert.equal(get("value-update").textContent, "Нет периодических UEV");
  assert.equal(get("value-pwm").textContent, "Нет повторения"); assert.equal(get("period-pwm").textContent, "Период не определён.");
});
test("Wrong blocked/periodic predictions are explained rather than accepted as measurements", () => {
  predict("72000000", "1000000", "periodic", "1000000"); submit();
  assert.match(get("comparison-update").textContent, /при ARR=0 он блокирован/);
  input("arr", "999"); predict("72000000", "1000000", "blocked"); submit();
  assert.match(get("comparison-update").textContent, /счёт периодический/);
});
test("Invalid registers and prediction inputs never expose computed results", () => {
  input("psc", "65536"); predict(); submit(); assert.equal(focused, "psc"); assert.equal(get("result").hidden, true);
  input("psc", "71"); predict("", "1000000"); submit(); assert.equal(focused, "pred-timer"); assert.equal(get("result").hidden, true);
  predict("72000000", "1000000", "periodic", ""); submit(); assert.equal(focused, "pred-update"); assert.equal(get("result").hidden, true);
});
test("Full-range registers and comma decimals retain a nonzero low frequency", () => {
  input("profile", "hsi8"); input("psc", "65535"); input("arr", "65535");
  predict("8000000", "122,0703125", "periodic", "0,001862645149230957"); submit();
  assert.equal(get("result").hidden, false); assert.match(get("value-update").textContent, /^0,001862/);
  assert.match(get("period-pwm").textContent, /536,870912/);
});
test("Clear keeps chosen profile/timer, clears predictions/registers and focuses PSC", () => {
  get("clear").handlers.click(); assert.equal(focused, "psc"); assert.equal(get("result").hidden, true);
  for (const id of ["psc", "arr", "pred-timer", "pred-counter", "pred-state", "pred-update"]) assert.equal(get(id).value, "");
  assert.equal(get("profile").value, "hsi8"); assert.equal(get("timer").value, "TIM1");
});
console.log(`\n${count} UI handler tests passed. DOM harness only; not a browser/rendering or screen-reader test.`);
