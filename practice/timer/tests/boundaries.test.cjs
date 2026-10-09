"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");
const core = html.match(/<script id="timer-core">([\s\S]*?)<\/script>/)[1];
const ui = html.match(/<script id="timer-ui">([\s\S]*?)<\/script>/)[1];
const math = vm.runInNewContext(`${core}\nTimerMath;`);
let count = 0;
function test(name, fn) { fn(); console.log(`ok ${++count} - ${name}`); }
const near = (a,b) => assert.ok(Math.abs(a-b) <= Math.abs(b)*1e-13, `${a} != ${b}`);
test("Exact-denominator oracle across every PSC value and ARR boundaries in both profiles", () => {
  for (const [profile,hz] of [["hsi8",8000000],["hse72",72000000]]) {
    for (let psc=0; psc<65536; psc++) for (const arr of [0,1,65534,65535]) {
      const r=math.calculate(profile,"TIM2",psc,arr);
      const den=Number((BigInt(psc)+1n)*(BigInt(arr)+1n));
      assert.equal(r.timerHz,hz); assert.equal(r.prescalerDiv,psc+1);
      near(r.counterHz,hz/(psc+1));
      if (!arr) {assert.equal(r.blocked,true);assert.equal(r.updateHz,null);assert.equal(r.periodSeconds,null);}
      else {assert.equal(r.blocked,false);assert.equal(r.updateHz,hz/den);assert.equal(r.pwmHz,hz/den);assert.equal(r.periodSeconds,den/hz);}
    }
  }
});
test("Every ARR value and minimum/maximum PSC agree for TIM1 and TIM3 at HSE72", () => {
  for (const timer of ["TIM1","TIM3"]) for (const psc of [0,65535]) for (let arr=0;arr<65536;arr++) {
    const r=math.calculate("hse72",timer,psc,arr);
    assert.equal(r.bus,timer==="TIM1"?"APB2":"APB1");
    assert.equal(r.updateHz,arr ? 72000000/Number((BigInt(psc)+1n)*(BigInt(arr)+1n)) : null);
  }
});
test("Every 16-bit register value round-trips through the shipped parser", () => {
  for (let i=0;i<65536;i++) assert.equal(math.parseRegister(String(i)),i);
  for(const invalid of ["000000","1\n2","١","１","1_000","0b10","0o77","0x10","+0","-0","\u200b7","<b>7</b>"])
    assert.throws(()=>math.parseRegister(invalid));
});
test("Frequency parser rejects partial numbers, zero and injection strings; accepts full decimal range within UI length", () => {
  for(const invalid of [".5","1.","1,","1,2.3","1\n2","5e-3","1_000","-0","\u200b7","<img src=x>","0".repeat(32)])
    assert.throws(()=>math.parseFrequency(invalid));
  for(const value of ["0.000000000000000000000000000001","9".repeat(32),"0000.1","0000,1"])
    assert.ok(Number.isFinite(math.parseFrequency(value))&&math.parseFrequency(value)>0);
});
// Independent small DOM double. It does not implement HTML layout, real browser events,
// focus scrolling, constraint validation, accessibility APIs, or browser state restoration.
function harness() {
  const nodes = new Map(); let focused=null;
  for (const [,tag,attrs,id] of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    assert.ok(!nodes.has(id));
    nodes.set(id, {id,tag,value:"",textContent:"",hidden:/\bhidden\b/.test(attrs),disabled:/\bdisabled\b/.test(attrs),required:/\brequired\b/.test(attrs),attrs:{},listeners:{},
      addEventListener(type, fn){(this.listeners[type]??=[]).push(fn);},
      setAttribute(name,value){this.attrs[name]=value;}, removeAttribute(name){delete this.attrs[name];}, focus(){focused=id;}});
  }
  const get=id=>{assert.ok(nodes.has(id),id);return nodes.get(id);};
  const labels=new Map([...html.matchAll(/<label for="([^"]+)">([^<]*)<\/label>/g)].map(m=>[m[1],{textContent:m[2]}]));
  get("practice").reset=()=>{for(const n of nodes.values())if(["input","select"].includes(n.tag))n.value="";get("profile").value="hsi8";get("timer").value="TIM2";};
  get("practice").querySelectorAll=()=>[...nodes.values()].filter(n=>n.attrs["aria-invalid"]==="true");
  const document={getElementById:get, querySelector:q=>labels.get(q.match(/^label\[for="([^"]+)"\]$/)[1])};
  vm.runInNewContext(`${core}\n${ui}`, {document,Intl});
  function dispatch(id,type){for(const fn of get(id).listeners[type]||[])fn({preventDefault(){}});}
  const input=(id,value)=>{get(id).value=value;dispatch(id,"input");};
  const submit=()=>dispatch("practice","submit");
  const config=(profile="hsi8",timer="TIM2",psc="7",arr="999")=>{for(const [id,val]of Object.entries({profile,timer,psc,arr}))input(id,val);};
  const prediction=(state="periodic",update="1000")=>{input("pred-timer","8000000");input("pred-counter","1000000");input("pred-state",state);if(state==="periodic")input("pred-update",update);};
  return {get,input,submit,dispatch,config,prediction,focused:()=>focused};
}
test("Each of the four configuration handlers clears all predictions and old result", () => {
  for(const [id,val] of [["profile","hse72"],["timer","TIM3"],["psc","8"],["arr","1000"]]) {
    const h=harness();h.config();h.prediction();h.submit();assert.equal(h.get("result").hidden,false);h.input(id,val);
    for(const pred of ["pred-timer","pred-counter","pred-state","pred-update"])assert.equal(h.get(pred).value,"");
    assert.equal(h.get("result").hidden,true);assert.equal(h.get("pred-update").disabled,true);
    h.submit();assert.equal(h.get("result").hidden,true);assert.equal(h.focused(),"pred-timer");
  }
});
test("Each prediction handler hides stale results, including state transitions", () => {
  for(const [id,val] of [["pred-timer","72000000"],["pred-counter","2000000"],["pred-state","blocked"],["pred-update","2000"]]) {
    const h=harness();h.config();h.prediction();h.submit();h.input(id,val);assert.equal(h.get("result").hidden,true);
    if(id==="pred-state"){assert.equal(h.get("pred-update").value,"");assert.equal(h.get("pred-update").disabled,true);}
  }
});
test("Repeated submit and repeated clear are stable and preserve only selected clock/timer", () => {
  const h=harness();h.config("hse72","TIM3","71","999");h.prediction();
  for(let i=0;i<5;i++){h.submit();assert.equal(h.get("result").hidden,false);assert.equal(h.get("error").hidden,true);assert.equal(h.focused(),"result-heading");}
  for(let i=0;i<5;i++){h.dispatch("clear","click");assert.equal(h.get("result").hidden,true);assert.equal(h.get("error").hidden,true);assert.equal(h.focused(),"psc");}
  assert.equal(h.get("profile").value,"hse72");assert.equal(h.get("timer").value,"TIM3");h.submit();assert.equal(h.focused(),"psc");
});
test("All register/prediction fields mark and focus their own error without revealing results", () => {
  for(const [id,value] of [["psc","-1"],["arr","65536"],["pred-timer","0"],["pred-counter","1e6"],["pred-state",""],["pred-update","bad"]]) {
    const h=harness();h.config();h.prediction();h.submit();h.input(id,value);
    // Config edits clear predictions, so refill them to isolate register validation.
    if(["psc","arr"].includes(id))h.prediction();h.submit();
    assert.equal(h.get(id).attrs["aria-invalid"],"true");assert.equal(h.focused(),id);assert.equal(h.get("result").hidden,true);assert.equal(h.get("error").hidden,false);
    h.dispatch("clear","click");assert.equal(h.get(id).attrs["aria-invalid"],undefined);assert.equal(h.get("error").hidden,true);
  }
});
test("All profile/timer maximum and minimum-running outputs stay finite and nonzero", () => {
  for(const profile of ["hsi8","hse72"])for(const timer of ["TIM1","TIM2","TIM3"])for(const [psc,arr] of [["0","1"],["65535","65535"]]) {
    const h=harness();h.config(profile,timer,psc,arr);h.prediction();h.submit();assert.equal(h.get("result").hidden,false);
    for(const id of ["value-timer","value-counter","value-update","value-pwm","period-pwm"]){assert.ok(!/NaN|Infinity/.test(h.get(id).textContent));assert.ok(h.get(id).textContent.length);}
    assert.equal(h.get("zero-notice").hidden,true);assert.equal(h.get("pwm-notice").hidden,false);
  }
});
test("ARR0 and periodic transitions toggle both notices and require fresh update predictions", () => {
  const h=harness();h.config("hsi8","TIM2","0","0");h.prediction("blocked");h.submit();assert.equal(h.get("zero-notice").hidden,false);assert.equal(h.get("pwm-notice").hidden,true);
  assert.match(h.get("comparison-counter").textContent,/не считает/);
  h.input("arr","1");h.prediction("periodic","");h.submit();assert.equal(h.get("result").hidden,true);assert.equal(h.focused(),"pred-update");
  h.input("pred-update","4000000");h.submit();assert.equal(h.get("zero-notice").hidden,true);assert.equal(h.get("pwm-notice").hidden,false);
});
test("Extreme but valid 32-character predictions cannot inject markup or produce NaN/Infinity", () => {
  const h=harness();h.config("hsi8","TIM3","65535","65535");h.prediction();
  for(const id of ["pred-timer","pred-counter","pred-update"])h.input(id,"9".repeat(32));h.submit();assert.equal(h.get("result").hidden,false);
  for(const id of ["comparison-timer","comparison-counter","comparison-update"])assert.ok(!/NaN|Infinity/.test(h.get(id).textContent));
});
test("Source retains programmatic labels, native controls, gated result, single breakpoint and no animation", () => {
  for(const id of ["profile","timer","psc","arr","pred-timer","pred-counter","pred-state","pred-update"])
    assert.match(html,new RegExp(`<label for="${id}">`));
  assert.match(html,/<h2 id="result-heading" tabindex="-1">/);assert.match(html,/id="error"[^>]*role="alert"[^>]*hidden/);
  assert.match(html,/@media\(max-width:600px\)/);assert.match(html,/\[hidden\]\{display:none!important\}/);assert.match(html,/:focus-visible\{/);
  assert.ok(!/innerHTML|insertAdjacentHTML|eval\(/.test(core+ui));assert.ok(!/animation\s*:|transition\s*:/.test(html));
});
console.log(`\n${count} independent boundary/source-handler tests passed. Exhaustive sweeps: 786432 math cases and 65536 register parses. No browser, mobile layout, assistive technology, or hardware acceptance claimed.`);
