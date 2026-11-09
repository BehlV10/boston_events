// Headless-Chrome check of the Near Me / dropped-pin list, driven over the DevTools protocol.
//   node tests/browser/near_me.mjs <chrome> <page.html> <port> <lat,lng>
// Prints JSON: each event row's distance in list order, how the list reacts to a filter change,
// and whether the rows were reused (built once per origin) or rebuilt.
import { spawn } from "node:child_process";
const [,, chromePath, file, port, pin] = process.argv;
const chrome = spawn(chromePath, ["--headless=new", "--no-sandbox", `--remote-debugging-port=${port}`,
  `--user-data-dir=${process.env.TMPDIR || "/tmp"}/near-me-${port}`, "--no-first-run", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const done = (out, code = 0) => { console.log(JSON.stringify(out)); chrome.kill(); process.exit(code); };
setTimeout(() => done({ error: "timeout" }, 1), 45000);
let targets;
for (let i = 0; i < 80 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(250); }
}
if (!targets) done({ error: "chrome did not start" }, 1);
const ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = m => { const d = JSON.parse(m.data); if (pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send("Page.enable");
await send("Page.navigate", { url: `file://${file}#pin=${pin}` });
await sleep(3000);
const r = (await send("Runtime.evaluate", { awaitPromise: true, returnByValue: true, expression: `(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const rows = () => Array.from(document.querySelectorAll('.near-events-list .event:not(.hidden)'));
  const read = () => rows().map(e => ({ id: e.dataset.id, bucket: e.dataset.bucket,
    miles: e.querySelector('.dist-badge') ? parseFloat(e.querySelector('.dist-badge').title) : null }));
  const banner = () => (document.querySelector('.near-stream-banner') || {}).innerText || '';
  const first = read();
  const probe = rows()[0]; if (probe) probe._probe = 1;
  const chk = Array.from(document.querySelectorAll('.cat-chk')).find(c => c.checked && first.some(r => r.bucket === c.value));
  let without = null, cat = null;
  if (chk) {
    cat = chk.value;
    chk.checked = false; chk.dispatchEvent(new Event('change', { bubbles: true })); await sleep(300);
    without = read();
    chk.checked = true; chk.dispatchEvent(new Event('change', { bubbles: true })); await sleep(300);
  }
  return { rows: first, banner: banner().replace(/\\s+/g, ' '), uncheckedCategory: cat, rowsWithCategoryOff: without,
           rowsRestored: read(), reused: !!(rows()[0] && rows()[0]._probe) };
})()` })).result;
done(r.exceptionDetails ? { error: r.exceptionDetails.exception?.description } : r.result.value, r.exceptionDetails ? 1 : 0);
