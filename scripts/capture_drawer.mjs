/**
 * 通过 Chrome DevTools Protocol 在无头浏览器里真实点击「详情」，
 * 截图抽屉，用来验证前端交互与渲染没有运行时错误。
 *
 * 用法：node scripts/capture_drawer.mjs <输出路径> [截图宽] [截图高]
 */

const [, , outPath = 'shots/drawer.png', width = '1500', height = '1350', portArg = '9222', rowArg = '0'] = process.argv;
const PORT = Number(portArg);
const ROW_INDEX = Number(rowArg);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function findPage() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const targets = await response.json();
      const page = targets.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch {
      /* 浏览器还没起来，继续等 */
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
  width: Number(width),
  height: Number(height),
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

// 等首屏数据渲染完成
for (let attempt = 0; attempt < 40; attempt += 1) {
  const rows = await evaluate("document.querySelectorAll('#resultBody tr').length");
  if (rows > 0) break;
  await sleep(300);
}

const rowCount = await evaluate("document.querySelectorAll('#resultBody tr').length");
console.log(`结果行数：${rowCount}`);
if (rowCount === 0) throw new Error('没有结果行，无法打开详情');

const clicked = await evaluate(`
  (() => {
    const rows = document.querySelectorAll('#resultBody tr');
    const row = rows[${ROW_INDEX}] || rows[0];
    if (!row) return false;
    row.click();
    return true;
  })()
`);
console.log(`点击详情：${clicked}`);

await sleep(1500);

const open = await evaluate("document.getElementById('drawer').getAttribute('aria-hidden')");
console.log(`抽屉 aria-hidden=${open}`);

const name = await evaluate("document.getElementById('drawerName').textContent");
const score = await evaluate("document.getElementById('drawerScore').textContent");
const rawReady = await evaluate("(document.querySelector('.drawer-body pre.raw')?.textContent || '').slice(0, 20)");
console.log(`抽屉内容：${name} / ${score} 分 / 原文片段：${rawReady}`);

const shot = await client.send('Page.captureScreenshot', { format: 'png' });
const { writeFile } = await import('node:fs/promises');
await writeFile(outPath, Buffer.from(shot.data, 'base64'));
console.log(`已保存 ${outPath}`);

client.close();
process.exit(0);
