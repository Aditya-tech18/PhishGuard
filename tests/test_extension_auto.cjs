/* Run: node --test tests/test_extension_auto.cjs. No browser or npm dependencies. */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const extension = path.join(__dirname, "../extension");
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function event() {
  const listeners = new Set();
  return { addListener: f => listeners.add(f), removeListener: f => listeners.delete(f),
    fire: (...args) => Promise.all([...listeners].map(f => f(...args))) };
}
async function harness(options = {}) {
  const local = { enabled: false, imageEnabled: false, notificationsEnabled: false };
  const session = { apiKey: "k".repeat(32) };
  const tabs = new Map((options.tabs || [{ id: 1, url: "https://one.test/login?token=secret#fragment" }]).map(x => [x.id, x]));
  const requests = [], warnings = [], notices = [], badges = new Map();
  let permission = options.permission !== false;
  const changed = event();
  const store = (data, area) => ({
    get: async names => Object.fromEntries((typeof names === "string" ? [names] : names).map(k => [k, data[k]])),
    set: async value => {
      const changes = Object.fromEntries(Object.entries(value).map(([k,v]) => [k, { oldValue: data[k], newValue: v }]));
      Object.assign(data, value); void changed.fire(changes, area);
    },
    setAccessLevel: async () => {}
  });
  const chrome = {
    storage: { local: store(local, "local"), session: store(session, "session"), onChanged: changed },
    runtime: { id: "fixture-id", onInstalled: event(), onStartup: event(), onMessage: event(), onMessageExternal: event(), getManifest: () => ({version:'2.6.0'}), getURL: x => "chrome-extension://fixture-id/" + x },
    tabs: { query: async query => query.active ? [...tabs.values()].slice(0,1) : [...tabs.values()],
      get: async id => { if (!tabs.has(id)) throw Error("closed"); return tabs.get(id); },
      onUpdated: event(), onRemoved: event(), onActivated: event(), update: async () => {},
      captureVisibleTab: async () => { throw Error("Automatic capture is forbidden"); } },
    permissions: { contains: async () => permission, onRemoved: event() },
    alarms: { create: async () => {}, clear: async () => {}, onAlarm: event() },
    scripting: { executeScript: async details => {
      if (details.func.name === "showPhishGuardWarning") warnings.push(details);
      return [];
    } },
    action: { setBadgeText: async ({ tabId,text }) => badges.set(tabId,text), setBadgeBackgroundColor: async () => {} },
    notifications: { onClicked: event(), getAll: async () => ({}), clear: async () => {}, create: async (...args) => notices.push(args) },
    windows: { update: async () => {} }
  };
  const context = vm.createContext({ chrome, URL, AbortController, console, crypto:require('node:crypto').webcrypto,performance,
    setTimeout: (f,ms) => setTimeout(f,ms===600 ? 3 : ms), clearTimeout,
    fetch: async (url, config) => {
      const item = { url, body: config.body && JSON.parse(config.body), signal: config.signal }; requests.push(item);
      const value = options.handler ? await options.handler(item) : { probability: .95, verdict: "phishing", reasons: ["Unusual hostname pattern"] };
      return { ok: true, json: async () => value };
    } });
  context.importScripts = (...names) => names.forEach(n => vm.runInContext(fs.readFileSync(path.join(extension,n),"utf8"),context));
  vm.runInContext(fs.readFileSync(path.join(extension,"background.js"),"utf8"),context);
  const send = payload => new Promise(resolve => {
    void chrome.runtime.onMessage.fire(payload,{ id: chrome.runtime.id, url: chrome.runtime.getURL("popup.html") },resolve);
  });
  return { chrome, local, session, tabs, requests, warnings, notices, badges, context, send,
    enable: async () => { const r=await send({type:"SET_ENABLED",enabled:true});assert.equal(r.ok,true);await pause(40); },
    stop: async () => { await send({type:"SET_ENABLED",enabled:false});await pause(10); },
    permission: value => { permission=value; } };
}
test("OFF performs no navigation requests or warnings", async () => {
  const h=await harness();await h.chrome.tabs.onUpdated.fire(1,{status:"complete"},h.tabs.get(1));await pause(20);
  assert.equal(h.requests.length,0);assert.equal(h.warnings.length,0);
});
test("ON checks existing tabs, sends origin only, and warns for phishing", async () => {
  const h=await harness();await h.enable();assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].body.url,"https://one.test/");assert.equal(h.warnings.length,1);
  assert.equal(h.warnings[0].args[1].title,"Yeh website scam ho sakti hai");await h.stop();
});
test("new tab/navigation is analyzed without clicking scan", async () => {
  const h=await harness();await h.enable();h.tabs.set(2,{id:2,url:"https://new.test/"});
  await h.chrome.tabs.onUpdated.fire(2,{url:"https://new.test/"},h.tabs.get(2));await pause(30);
  assert.equal(h.requests.length,2);assert.equal(h.warnings.at(-1).target.tabId,2);await h.stop();
});
test("low-risk result produces no warning or OS notification", async () => {
  const h=await harness({handler:async()=>({probability:.1,verdict:"low_risk"})});await h.enable();
  assert.equal(h.warnings.length,0);assert.equal(h.notices.length,0);assert.equal(h.badges.get(1),"");await h.stop();
});
test("permission denial cannot enable automatic checking", async () => {
  const h=await harness({permission:false});const r=await h.send({type:"SET_ENABLED",enabled:true});
  assert.equal(r.ok,false);assert.equal(h.local.enabled,false);assert.equal(h.requests.length,0);
});
test("missing session key cannot enable checking", async () => {
  const h=await harness();h.session.apiKey=undefined;const r=await h.send({type:"SET_ENABLED",enabled:true});assert.equal(r.ok,false);
});
test("OFF discards an in-flight phishing result", async () => {
  let resolve;const h=await harness({handler:()=>new Promise(r=>{resolve=r;})});await h.enable();await h.stop();
  resolve({probability:.99,verdict:"phishing"});await pause(25);assert.equal(h.warnings.length,0);assert.equal(h.requests[0].signal.aborted,true);
});
test("navigation discards a stale response from the old page", async () => {
  let resolve;let count=0;const h=await harness({handler:()=>++count===1?new Promise(r=>{resolve=r;}):Promise.resolve({probability:.1,verdict:"low_risk"})});
  await h.enable();h.tabs.set(1,{id:1,url:"https://different.test/"});
  await h.chrome.tabs.onUpdated.fire(1,{url:"https://different.test/"},h.tabs.get(1));
  resolve({probability:.99,verdict:"phishing"});await pause(35);assert.equal(h.warnings.length,0);await h.stop();
});
test("offline API is unavailable, never a safe verdict", async () => {
  const h=await harness({handler:async()=>{throw Error("offline");}});await h.enable();
  assert.equal(h.badges.get(1),"?");assert.equal(h.warnings.length,0);const r=await h.send({type:"GET_STATUS"});assert.equal(r.result.state,"unavailable");await h.stop();
});
test("invalid model response produces no warning", async () => {
  const h=await harness({handler:async()=>({probability:2,verdict:"phishing"})});await h.enable();assert.equal(h.warnings.length,0);await h.stop();
});
test("unsupported, credential-bearing and incognito tabs are skipped", async () => {
  const h=await harness({tabs:[{id:1,url:"chrome://settings"},{id:2,url:"https://user:secret@one.test/"},{id:3,url:"https://private.test/",incognito:true}]});
  await h.enable();assert.equal(h.requests.length,0);await h.stop();
});
test("network concurrency is bounded across many tabs", async () => {
  let running=0,maximum=0;const h=await harness({tabs:Array.from({length:12},(_,i)=>({id:i+1,url:`https://site${i}.test/`})),handler:async()=>{
    running++;maximum=Math.max(maximum,running);await pause(15);running--;return {probability:.1,verdict:"low_risk"};
  }});await h.enable();await pause(100);assert.equal(h.requests.length,12);assert.ok(maximum<=3);await h.stop();
});
test("repeat events do not spam warnings, key revocation aborts checking", async () => {
  const h=await harness();await h.enable();await h.chrome.tabs.onUpdated.fire(1,{status:"complete"},h.tabs.get(1));await pause(25);
  assert.equal(h.warnings.length,1);await h.chrome.storage.session.set({apiKey:undefined});await pause(15);
  await h.chrome.tabs.onUpdated.fire(1,{status:"complete"},h.tabs.get(1));await pause(15);assert.equal(h.requests.length,1);await h.stop();
});
test("browser notifications are optional and suspicious-only", async () => {
  const h=await harness();h.local.notificationsEnabled=true;await h.enable();assert.equal(h.notices.length,1);await h.stop();
});
test("alarm checks nothing when OFF and retries current tabs while ON", async () => {
  const h=await harness();await h.chrome.alarms.onAlarm.fire({name:"phishguard-active-recheck"});await pause(10);assert.equal(h.requests.length,0);
  await h.enable();vm.runInContext('for(const entry of entries.values())entry.completed=0;',h.context);
  await h.chrome.alarms.onAlarm.fire({name:"phishguard-active-recheck"});await pause(25);
  assert.equal(h.requests.length,2);assert.equal(h.warnings.length,1);await h.stop();
});
test("image consent is required and no screenshot is taken automatically", async () => {
  const h=await harness();await h.enable();h.local.imageEnabled=true;
  const r=await h.send({type:"SCAN_IMAGE",consent:false});assert.equal(r.ok,false);
  assert.ok(h.requests.every(x=>!x.url.includes("/image")));await h.stop();
});
test("OFF during screenshot capability check prevents capture and upload", async () => {
  let resolve,captures=0;
  const h=await harness({handler:item=>item.url.endsWith('/health')?new Promise(r=>{resolve=r;}):Promise.resolve({probability:.1,verdict:'low_risk'})});
  await h.enable();h.local.imageEnabled=true;
  h.chrome.tabs.captureVisibleTab=async()=>{captures++;return 'data:image/jpeg;base64,aaa';};
  const pending=h.send({type:'SCAN_IMAGE',consent:true});await pause(10);await h.stop();resolve({vision_enabled:true});
  assert.equal((await pending).ok,false);assert.equal(captures,0);
});
test("changing the active tab during screenshot consent flow prevents capture", async () => {
  let resolve,captures=0;
  const h=await harness({handler:item=>item.url.endsWith('/health')?new Promise(r=>{resolve=r;}):Promise.resolve({probability:.1,verdict:'low_risk'})});
  await h.enable();h.local.imageEnabled=true;
  h.chrome.tabs.captureVisibleTab=async()=>{captures++;return 'data:image/jpeg;base64,aaa';};
  const pending=h.send({type:'SCAN_IMAGE',consent:true});await pause(10);
  h.tabs.clear();h.tabs.set(2,{id:2,url:'https://other.test/'});resolve({vision_enabled:true});
  assert.equal((await pending).ok,false);assert.equal(captures,0);await h.stop();
});
test("an untrusted sender cannot enable checks", async () => {
  const h=await harness();let responded=false;
  await h.chrome.runtime.onMessage.fire({type:'SET_ENABLED',enabled:true},{id:'other',url:'https://untrusted.test/'},()=>{responded=true;});
  assert.equal(responded,false);assert.equal(h.local.enabled,false);assert.equal(h.requests.length,0);
});
test("malformed image capability cannot trigger screenshot capture", async () => {
  let captures=0;
  const h=await harness({handler:async item=>item.url.endsWith('/health')?{vision_enabled:'true'}:{probability:.1,verdict:'low_risk'}});
  await h.enable();h.local.imageEnabled=true;h.chrome.tabs.captureVisibleTab=async()=>{captures++;return 'data:image/jpeg;base64,aaa';};
  assert.equal((await h.send({type:'SCAN_IMAGE',consent:true})).ok,false);assert.equal(captures,0);await h.stop();
});
