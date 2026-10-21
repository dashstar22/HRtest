/**
 * 人工标注的端到端验证：
 *   1. 点击列表里的「采纳」
 *   2. 校验统计与徽标
 *   3. 通过 API 修改 JD（模拟 HR 改条件）
 *   4. 刷新页面，校验过期提示出现、且人工标注仍在
 *
 * 用法：node scripts/capture_decision.mjs <输出前缀> [调试端口]
 */

const [, , prefix = 'docs/decision', portArg = '9224'] = process.argv;
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
      /* 等浏览器启动 */
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
  await evaluate("document.querySelector('.results-card').scrollIntoView({ block: 'start' })");
  await sleep(500);
  const shot = await client.send('Page.captureScreenshot', { format: 'png' });
  const { writeFile } = await import('node:fs/promises');
  await writeFile(path, Buffer.from(shot.data, 'base64'));
  console.log(`已保存 ${path}`);
}

await sleep(1200);
const rowCount = await evaluate("document.querySelectorAll('#resultBody tr').length");
console.log('初始结果行数:', rowCount);
if (rowCount === 0) throw new Error('没有结果行');

const accepted = await evaluate(`(() => {
  const button = document.querySelector('#resultBody tr [data-decide="accepted"]');
  if (!button) return null;
  const resultId = button.dataset.id;
  button.click();
  return resultId;
})()`);
console.log('点击采纳的 resultId:', accepted);
await sleep(1500);

const afterAccept = await evaluate(`(() => {
  const row = document.querySelector('#resultBody tr');
  const badge = row.querySelector('.decision-cell .badge');
  return {
    acceptedStat: document.getElementById('statAccepted').textContent,
    rejectedStat: document.getElementById('statRejected').textContent,
    badge: badge ? badge.textContent.trim() : '',
    rowClass: row.className,
  };
})()`);
console.log('标注后:', JSON.stringify(afterAccept));
await shoot(`${prefix}-accepted.png`);

const jobId = await evaluate("document.getElementById('jobSelect').value");
const putStatus = await evaluate(`(async () => {
  const job = await (await fetch('/api/jobs/${jobId}')).json();
  job.min_years = 8;
  const response = await fetch('/api/jobs/${jobId}', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  });
  return response.status;
})()`);
console.log('修改 JD（年限 5→8）状态码:', putStatus);

await client.send('Page.reload', { ignoreCache: true });
await sleep(2500);

const afterReload = await evaluate(`(() => {
  const banner = document.getElementById('staleBanner');
  const row = document.querySelector('#resultBody tr');
  const badge = row.querySelector('.decision-cell .badge');
  return {
    bannerVisible: !banner.hidden,
    bannerText: banner.textContent.trim().replace(/\\s+/g, ' ').slice(0, 60),
    staleRows: document.querySelectorAll('#resultBody tr.stale').length,
    firstRowDecision: badge ? badge.textContent.trim() : '(未标注)',
    acceptedStat: document.getElementById('statAccepted').textContent,
  };
})()`);
console.log('改 JD 后刷新:', JSON.stringify(afterReload));
await shoot(`${prefix}-stale.png`);

client.close();
process.exit(0);
