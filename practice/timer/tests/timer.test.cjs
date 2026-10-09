"use strict";
// No packages required. Test the exact pure calculation code shipped in index.html.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const core = html.match(/<script id="timer-core">([\s\S]*?)<\/script>/);
assert.ok(core, "The delivered HTML must contain the tested core.");
const math = vm.runInNewContext(`${core[1]}\nTimerMath;`, {}, { timeout: 1000 });
let count = 0;
function test(name, run) { run(); count++; console.log(`ok ${count} - ${name}`); }
function near(actual, expected) {
  assert.ok(Math.abs(actual - expected) <= Math.max(1e-12, Math.abs(expected) * 1e-12), `${actual} != ${expected}`);
}
const calculate = math.calculate;

test("Only the two course clock profiles exist", () => {
  assert.deepEqual(Object.keys(math.profiles), ["hsi8", "hse72"]);
  assert.ok(Object.isFrozen(math.profiles));
  for (const profile of Object.values(math.profiles)) assert.ok(Object.isFrozen(profile));
});
test("HSI8: all three timers use 8 MHz and APB /1 has no doubling", () => {
  for (const timer of ["TIM1", "TIM2", "TIM3"]) {
    const c = math.clock("hsi8", timer);
    assert.equal(c.pclkHz, 8000000); assert.equal(c.timerHz, 8000000);
    assert.equal(c.apbDiv, 1); assert.equal(c.multiplier, 1);
  }
});
test("TIM1 is APB2; TIM2/TIM3 are APB1", () => {
  assert.equal(math.clock("hsi8", "TIM1").bus, "APB2");
  for (const timer of ["TIM2", "TIM3"]) assert.equal(math.clock("hsi8", timer).bus, "APB1");
});
test("HSE72 APB1: 36 MHz PCLK is doubled to 72 MHz timer input", () => {
  for (const timer of ["TIM2", "TIM3"]) {
    const c = math.clock("hse72", timer);
    assert.equal(c.hclkHz, 72000000); assert.equal(c.apbDiv, 2);
    assert.equal(c.pclkHz, 36000000); assert.equal(c.multiplier, 2); assert.equal(c.timerHz, 72000000);
  }
});
test("HSE72 TIM1 APB2: 72 MHz without doubling", () => {
  const c = math.clock("hse72", "TIM1");
  assert.equal(c.apbDiv, 1); assert.equal(c.pclkHz, 72000000);
  assert.equal(c.multiplier, 1); assert.equal(c.timerHz, 72000000);
});
test("Unknown clocks, arbitrary timers and object prototype names are rejected", () => {
  for (const bad of ["hsi72", "8000000", "__proto__", "constructor", "", null]) assert.throws(() => math.clock(bad, "TIM2"));
  for (const bad of ["TIM5", "TIM2_32bit", "__proto__", "constructor", "", null]) assert.throws(() => math.clock("hsi8", bad));
});
test("L05 HSI8 PSC7/ARR999: counter 1 MHz, update and PWM 1 kHz", () => {
  const r = calculate("hsi8", "TIM2", 7, 999);
  assert.equal(r.counterHz, 1000000); assert.equal(r.updateHz, 1000);
  assert.equal(r.pwmHz, 1000); assert.equal(r.periodSeconds, 0.001);
  assert.equal(r.prescalerDiv, 8); assert.equal(r.periodCounts, 1000); assert.equal(r.blocked, false);
});
test("Off-by-one PSC8 means /9, not /8", () => {
  const r = calculate("hsi8", "TIM2", 8, 999);
  near(r.updateHz, 8000000 / 9000); assert.notEqual(r.updateHz, 1000);
});
test("Off-by-one ARR1000 means 1001 counts", () => {
  const r = calculate("hsi8", "TIM2", 7, 1000);
  assert.equal(r.periodCounts, 1001); near(r.updateHz, 1000000 / 1001);
});
test("HSE72 PSC71/ARR999: all three timers give 1 kHz under stated RCR0 assumption", () => {
  for (const timer of ["TIM1", "TIM2", "TIM3"]) {
    const r = calculate("hse72", timer, 71, 999);
    assert.equal(r.counterHz, 1000000); assert.equal(r.updateHz, 1000);
  }
});
test("Reusing HSI values at HSE72 yields 9 kHz, not 1 kHz", () => {
  assert.equal(calculate("hse72", "TIM2", 7, 999).updateHz, 9000);
});
test("PSC0 is divisor 1; ARR1 is the smallest running period (2 counts)", () => {
  const r = calculate("hsi8", "TIM2", 0, 1);
  assert.equal(r.counterHz, 8000000); assert.equal(r.prescalerDiv, 1);
  assert.equal(r.periodCounts, 2); assert.equal(r.updateHz, 4000000);
});
test("ARR0 fits the register but blocks counting for every supported timer/profile", () => {
  for (const profile of ["hsi8", "hse72"]) for (const timer of ["TIM1", "TIM2", "TIM3"]) for (const psc of [0, 7, 65535]) {
    const r = calculate(profile, timer, psc, 0);
    assert.equal(r.blocked, true); assert.equal(r.updateHz, null);
    assert.equal(r.pwmHz, null); assert.equal(r.periodSeconds, null);
    assert.ok(r.counterHz > 0, "The prescaled clock must be distinguished from actual counter activity.");
  }
});
test("Both 16-bit register maxima produce /65536 × 65536, without 32-bit overflow", () => {
  const r = calculate("hsi8", "TIM3", 65535, 65535);
  assert.equal(r.prescalerDiv, 65536); assert.equal(r.periodCounts, 65536);
  assert.equal(r.counterHz, 122.0703125); assert.equal(r.updateHz, 0.001862645149230957);
  assert.equal(r.periodSeconds, 536.870912); assert.equal(r.prescalerDiv * r.periodCounts, 4294967296);
});
test("Largest divider on HSE72 has finite positive frequency", () => {
  const r = calculate("hse72", "TIM1", 65535, 65535);
  near(r.updateHz, 72000000 / 4294967296); near(r.periodSeconds, 4294967296 / 72000000);
});
test("Calculation rejects out-of-range, noninteger, nonnumeric and nonfinite registers", () => {
  for (const bad of [-1, 65536, 2 ** 32, 0.5, NaN, Infinity, -Infinity, "7", null, undefined, true]) {
    assert.throws(() => calculate("hsi8", "TIM2", bad, 999));
    assert.throws(() => calculate("hsi8", "TIM2", 7, bad));
  }
});
test("Register text accepts only complete decimal integers in range", () => {
  assert.equal(math.parseRegister("0"), 0); assert.equal(math.parseRegister("65535"), 65535);
  assert.equal(math.parseRegister(" 00007 "), 7);
  for (const bad of ["", " ", "-1", "+1", "65536", "1.0", "1,0", "1e3", "0xFF", "12abc", "65 535", "Infinity", null, 7]) assert.throws(() => math.parseRegister(bad));
});
test("Prediction parser accepts decimal dot/comma but never blank, zero or expressions", () => {
  assert.equal(math.parseFrequency("8000000"), 8000000);
  assert.equal(math.parseFrequency(" 888,889 "), 888.889); assert.equal(math.parseFrequency("0.001"), 0.001);
  for (const bad of ["", " ", "0", "0,0", "-1", "+1", "1e3", "1/2", "NaN", "Infinity", "12abc", "1,2,3", "1 000", "9".repeat(400), null, 1000]) assert.throws(() => math.parseFrequency(bad));
});
test("Result objects cannot be mutated to change clock assumptions", () => {
  const r = calculate("hsi8", "TIM2", 7, 999);
  assert.ok(Object.isFrozen(r)); assert.throws(() => { r.timerHz = 72000000; });
});
test("Sampled valid dividers obey exact integer-ratio formula and reciprocal period", () => {
  for (const profile of ["hsi8", "hse72"]) for (const psc of [0, 1, 7, 71, 255, 999, 65534, 65535]) for (const arr of [1, 2, 999, 1000, 32767, 65534, 65535]) {
    const r = calculate(profile, "TIM2", psc, arr);
    near(r.counterHz * (psc + 1), r.timerHz);
    near(r.updateHz * (psc + 1) * (arr + 1), r.timerHz);
    near(r.periodSeconds * r.updateHz, 1); assert.equal(r.pwmHz, r.updateHz);
  }
});
test("Single HTML has no external runtime dependencies or network/storage APIs", () => {
  assert.ok(!/<script[^>]+src=|<link[^>]+(?:stylesheet|preload)|<iframe|<form[^>]+action=/i.test(html));
  assert.ok(!/\b(fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage|indexedDB|sendBeacon)\b/.test(html));
  assert.match(html, /connect-src 'none'/); assert.match(html, /form-action 'none'/);
  assert.match(html, /<html lang="ru">/); assert.match(html, /<section id="result"[^>]*hidden>/);
});
console.log(`\n${count} tests passed. Arithmetic only; no hardware or assessment verification.`);
