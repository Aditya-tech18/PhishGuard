/* npm install --prefix tests/browser; node tests/browser_auto.cjs */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const { createRequire } = require("node:module");
const requireBrowser = createRequire(path.resolve(process.env.PHISHGUARD_BROWSER_PACKAGE || path.join(__dirname,"browser/package.json")));
const { chromium } = requireBrowser("playwright");
const wait = ms => new Promise(resolve => setTimeout(resolve,ms));
async function until(test, label, timeout=12000) {
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline) { if(await test()) return; await wait(40); }
  throw Error("Timeout: "+label);
}
class Popup {
  constructor(browser,page,session) {
    this.browser=browser;this.page=page;this.session=session;this.responses=new Map();this.sequence=0;
    browser.on("Target.receivedMessageFromTarget", event=>{
      if(event.sessionId!==this.session)return;
      const m=JSON.parse(event.message);if(m.id)this.responses.set(m.id,m);
    });
  }
  async evaluate(expression) {
    const id=++this.sequence;
    await this.browser.send("Target.sendMessageToTarget",{sessionId:this.session,message:JSON.stringify({id,method:"Runtime.evaluate",params:{expression,returnByValue:true,awaitPromise:true,userGesture:true}})});
    await until(()=>this.responses.has(id),"popup evaluation");
    const result=this.responses.get(id);this.responses.delete(id);
    if(result.error||result.result?.exceptionDetails)throw Error(JSON.stringify(result));
    return result.result?.result?.value;
  }
}
async function main() {
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),"pg-auto-browser-"));
  const requests=[],verdicts=[];let context;
  const key="isolated-browser-fixture-"+"k".repeat(40);
  const server=http.createServer(async(req,res)=>{
    let body="";for await(const chunk of req)body+=chunk;
    res.setHeader("Content-Type","application/json");
    if(req.url==="/health"){res.end(JSON.stringify({vision_enabled:false}));return;}
    if(req.headers["x-api-key"]!==key){res.statusCode=401;res.end("{}");return;}
    const payload=JSON.parse(body);requests.push(payload);
    if(req.url.includes("image"))throw Error("Automatic screenshots must never occur");
    const bad=payload.url.includes("scam");
    if(payload.url.includes("slow"))await wait(1600);
    res.end(JSON.stringify({probability:bad?.94:.08,verdict:bad?"phishing":"low_risk",model_version:"isolated-browser-fixture",reasons:bad?["<img src=x onerror=alert(1)> Suspicious hostname pattern (test fixture)"]:[]}));
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  try {
    const source=path.resolve(__dirname,"../extension"),extension=path.join(temp,"extension");
    await fs.cp(source,extension,{recursive:true});
    const manifest=JSON.parse(await fs.readFile(path.join(extension,"manifest.json"),"utf8"));
    const port=server.address().port;
    // Test-only pregrants avoid automating a native permission dialog. Shipping manifest stays optional.
    manifest.host_permissions=["http://*/*","https://*/*"];
    await fs.writeFile(path.join(extension,"manifest.json"),JSON.stringify(manifest));
    let workerCode=await fs.readFile(path.join(extension,"background.js"),"utf8");
    workerCode=workerCode.replace('const API = "http://127.0.0.1:8000";',`const API = "http://127.0.0.1:${port}";`);
    await fs.writeFile(path.join(extension,"background.js"),workerCode);
    context=await chromium.launchPersistentContext(path.join(temp,"profile"),{channel:"chromium",headless:true,args:[
      `--disable-extensions-except=${extension}`,`--load-extension=${extension}`,"--enable-unsafe-extension-debugging","--disable-background-networking"]});
    await context.route("https://**/*.test/**",route=>route.fulfill({status:200,contentType:"text/html",body:"<!doctype html><html><body><h1>Isolated test website</h1></body></html>"}));
    const worker=context.serviceWorkers()[0]||await context.waitForEvent("serviceworker");
    const extensionId=worker.url().split("/")[2];
    const page=await context.newPage();await page.goto("https://normal.test/login?private=do-not-send#secret");
    await wait(900);assert.equal(requests.length,0);verdicts.push("OFF: zero automatic requests");
    const browser=await context.browser().newBrowserCDPSession();
    const targets=await browser.send("Target.getTargets",{filter:[{type:"tab",exclude:false}]});
    const target=targets.targetInfos.find(t=>t.url.startsWith("https://normal.test"));assert.ok(target);
    await browser.send("Extensions.triggerAction",{id:extensionId,targetId:target.targetId});
    let popupTarget;
    await until(async()=>{popupTarget=(await browser.send("Target.getTargets")).targetInfos.find(t=>t.url.endsWith("/popup.html"));return !!popupTarget;},"toolbar popup");
    const session=(await browser.send("Target.attachToTarget",{targetId:popupTarget.targetId,flatten:false})).sessionId;
    const popup=new Popup(browser,page,session);
    await until(async()=>await popup.evaluate('document.readyState === "complete"'),"popup ready");
    await popup.evaluate(`document.getElementById("key").value=${JSON.stringify(key)};document.getElementById("save").click()`);
    await until(async()=>await popup.evaluate('document.getElementById("key").value === ""'),"key saved");
    await popup.evaluate('document.getElementById("enabled").click()');
    await wait(500);
    await until(()=>requests.length>=1,"ON existing-tab scan");
    assert.deepEqual(requests[0],{url:"https://normal.test/"});
    assert.equal(await page.locator('[data-phishguard-warning]').count(),0);
    verdicts.push("Actual popup ON scans existing tab; origin-only payload; no low-risk popup");
    const scam=await context.newPage();await scam.goto("https://scam.test/login?token=private#secret");
    await until(async()=>await scam.locator('[data-phishguard-warning]').count()===1,"new-tab scam warning");
    const warningText=await worker.evaluate(async()=>{
      const tabs=await chrome.tabs.query({});const tab=tabs.find(t=>t.url?.startsWith("https://scam.test/"));
      return (await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>globalThis.__phishGuardWarning.root.textContent}))[0].result;
    });
    assert.match(warningText,/Yeh website scam ho sakti hai/);assert.match(warningText,/<img src=x onerror=alert\(1\)>/);
    verdicts.push("Real new-tab page warning; friendly wording; model reason rendered as inert text");
    if(process.env.PHISHGUARD_WARNING_SCREENSHOT)await scam.screenshot({path:process.env.PHISHGUARD_WARNING_SCREENSHOT});
    await worker.evaluate(async()=>{
      const tabs=await chrome.tabs.query({}),tab=tabs.find(t=>t.url?.startsWith("https://scam.test/"));
      await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>globalThis.__phishGuardWarning.root.querySelector('.row button:last-child').click()});
    });
    assert.equal(await scam.locator('[data-phishguard-warning]').count(),0);
    await scam.goto("https://another-scam.test/");
    await until(async()=>await scam.locator('[data-phishguard-warning]').count()===1,"navigation recheck");
    await worker.evaluate(()=>chrome.storage.local.set({enabled:false}));
    await until(async()=>await scam.locator('[data-phishguard-warning]').count()===0,"OFF removes warning");
    const count=requests.length;await scam.goto("https://off-scam.test/");await wait(1000);assert.equal(requests.length,count);
    verdicts.push("Dismiss works; navigation rechecks; OFF removes warning and stops new requests");
    await worker.evaluate(()=>chrome.storage.local.set({enabled:true}));
    await until(()=>requests.length>count,"re-enable");
    const slow=await context.newPage();await slow.goto("https://slow-scam.test/");
    await until(()=>requests.some(x=>x.url==="https://slow-scam.test/"),"slow request starts");
    await slow.goto("https://different.test/");await wait(1900);
    assert.equal(await slow.locator('[data-phishguard-warning]').count(),0);
    verdicts.push("Late phishing response discarded after navigation");
    await slow.goto("https://slow-scam-off.test/");
    await until(()=>requests.some(x=>x.url==="https://slow-scam-off.test/"),"pending OFF request");
    await worker.evaluate(()=>chrome.storage.local.set({enabled:false}));await wait(1900);
    assert.equal(await slow.locator('[data-phishguard-warning]').count(),0);
    verdicts.push("Late phishing response discarded after OFF");
    const sensitive=await worker.evaluate(async()=>({local:await chrome.storage.local.get(null),session:await chrome.storage.session.get(null)}));
    assert.equal(JSON.stringify(sensitive).includes("scam.test"),false);
    assert.ok(requests.every(x=>Object.keys(x).length===1&&new URL(x.url).pathname==="/"&&!new URL(x.url).search));
    verdicts.push("No browsing results/URLs stored; no automatic screenshots");
    const result={passed:true,checks:verdicts,playwright:requireBrowser("playwright/package.json").version,
      chromium:context.browser().version(),native_optional_permission_prompt_automated:false,
      fixture_policy:"Isolated profile; pregranted website hosts and ephemeral deterministic local API; synthetic .test pages only",
      live_phishing_sites_visited:false,personal_browser_profile_used:false};
    if(process.env.PHISHGUARD_BROWSER_REPORT)await fs.writeFile(process.env.PHISHGUARD_BROWSER_REPORT,JSON.stringify(result,null,2)+"\n");
    console.log(JSON.stringify(result,null,2));
  } finally {await context?.close();await new Promise(resolve=>server.close(resolve));await fs.rm(temp,{recursive:true,force:true});}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
