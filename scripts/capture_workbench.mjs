/**
 * 复核工作台端到端验证：批量标注、搜索、备注、重新筛选后的变化追踪。
 *
 * 用法：node scripts/capture_workbench.mjs <输出前缀> [调试端口]
 */

const [, , prefix = 'docs/workbench', portArg = '9228'] = process.argv;
const PORT = Number(portArg);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function findPage() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const targets = await response.json();
      const page = targets.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch {
      /* 等浏览器 */
    }
    await sleep(300);
  }
  throw new Error('未找到可调试的页面');
}

function connect(url) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    const pending = new Map();
    let nextId = 1;

    socket.addEventListener('open', () => {
      resolve({
        send(method, params = {}) {
          const id = nextId++;
          socket.send(JSON.stringify({ id, method, params }));
          return new Promise((res, rej) => pending.set(id, { res, rej }));
        },
        close: () => socket.close(),
      });
    });

    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      const entry = pending.get(message.id);
      if (!entry) return;
      pending.delete(message.id);
      if (message.error) entry.rej(new Error(JSON.stringify(message.error)));
      else entry.res(message.result);
    });

    socket.addEventListener('error', reject);
  });
}

const page = await findPage();
const client = await connect(page.webSocketDebuggerUrl);
await client.send('Page.enable');
await client.send('Runtime.enable');
await client.send('Emulation.setDeviceMetricsOverride', {
  width: 1500,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});

async function evaluate(expression) {
  const result = await client.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || 'JS 执行异常');
  }
  return result.result.value;
}

async function shoot(path) {
  await evaluate("document.querySelector('.results-card')?.scrollIntoView({ block: 'start' })");
  await sleep(450);
  const shot = await client.send('Page.captureScreenshot', { format: 'png' });
  const { writeFile } = await import('node:fs/promises');
  await writeFile(path, Buffer.from(shot.data, 'base64'));
  console.log(`已保存 ${path}`);
}

await sleep(1500);
console.log('结果行数:', await evaluate("document.querySelectorAll('#resultBody tr').length"));

/* 1. 勾选前两行 → 批量条出现 */
const selected = await evaluate(`(() => {
  const boxes = [...document.querySelectorAll('#resultBody [data-select]')].slice(0, 2);
  boxes.forEach((box) => {
    box.checked = true;
    box.dispatchEvent(new Event('change', { bubbles: true }));
  });
  return boxes.length;
})()`);
await sleep(300);
const bulk = await evaluate(`(() => ({
  visible: !document.getElementById('bulkBar').hidden,
  count: document.getElementById('bulkCount').textContent,
  checked: document.querySelectorAll('#resultBody [data-select]:checked').length,
}))()`);
console.log('已勾选:', selected, JSON.stringify(bulk));
await shoot(`${prefix}-bulk.png`);

await evaluate(`document.querySelector('[data-bulk="rejected"]').click()`);
await sleep(1800);
console.log('批量拒绝后统计:', JSON.stringify(await evaluate(`(() => ({
  accepted: document.getElementById('statAccepted').textContent,
  rejected: document.getElementById('statRejected').textContent,
  bulkVisible: !document.getElementById('bulkBar').hidden,
}))()`)));

/* 2. 搜索过滤 */
await evaluate(`(() => {
  const input = document.getElementById('searchInput');
  input.value = 'Python';
  input.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(300);
console.log('搜索 Python 后行数:', await evaluate("document.querySelectorAll('#resultBody tr').length"));
await evaluate(`(() => {
  const input = document.getElementById('searchInput');
  input.value = '';
  input.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(300);

/* 3. 打开详情写备注 */
await evaluate("document.querySelector('#resultBody tr').click()");
await sleep(1200);
const noteResult = await evaluate(`(() => {
  const area = document.getElementById('noteEditor');
  if (!area) return 'no-editor';
  if (area.disabled) return 'disabled';
  area.value = '电话沟通后确认 3 周内到岗，期望薪资在预算内';
  document.getElementById('saveNoteBtn').click();
  return 'saved';
})()`);
await sleep(1800);
console.log('备注保存:', noteResult);
await shoot(`${prefix}-note.png`);
await evaluate("document.getElementById('drawer').setAttribute('aria-hidden', 'true'); document.body.style.overflow = '';");

/* 4. 改 JD → 重新筛选，检查变化追踪 */
const jobId = await evaluate("document.getElementById('jobSelect').value");
await evaluate(`(async () => {
  const job = await (await fetch('/api/jobs/${jobId}')).json();
  job.min_years = 8;
  const response = await fetch('/api/jobs/${jobId}', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  });
  return response.status;
})()`);
await sleep(600);
await evaluate("document.getElementById('staleScreenBtn').click()");
await sleep(3500);

const changed = await evaluate(`(() => ({
  hint: document.getElementById('changeHint').textContent,
  deltas: [...document.querySelectorAll('.delta')].map((node) => node.textContent),
  shifts: document.querySelectorAll('.score-shift').length,
  rowCount: document.querySelectorAll('#resultBody tr').length,
}))()`);
console.log('重新筛选后:', JSON.stringify(changed));
await shoot(`${prefix}-changed.png`);

client.close();
process.exit(0);
