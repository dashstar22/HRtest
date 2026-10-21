/**
 * 上传链路验证：通过 CDP 真实选择文件，检查「未筛选简历」提示、PDF 解析与删除恢复。
 *
 * 用法：node scripts/capture_upload.mjs <PDF 路径> [调试端口]
 */

const [, , pdfPath = 'samples/extra/resume_赵磊.pdf', portArg = '9231'] = process.argv;
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
await client.send('DOM.enable');
await client.send('Emulation.setDeviceMetricsOverride', {
  width: 1500,
  height: 1080,
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

await sleep(1500);
const before = await evaluate(`(() => ({
  resumes: document.getElementById('resumeCount').textContent,
  hint: document.getElementById('pendingHint').textContent,
}))()`);
console.log('上传前:', JSON.stringify(before));

// 关掉 confirm，便于后续删除
await evaluate("window.confirm = () => true;");

const { root } = await client.send('DOM.getDocument');
const { nodeId } = await client.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#fileInput' });
// Windows 下必须传原生绝对路径，转成 file:// URL 反而会让浏览器读不到文件
await client.send('DOM.setFileInputFiles', { nodeId, files: [pdfPath] });
await sleep(2500);

const after = await evaluate(`(() => ({
  resumes: document.getElementById('resumeCount').textContent,
  hint: document.getElementById('pendingHint').textContent,
  hintClass: document.getElementById('pendingHint').className,
  items: [...document.querySelectorAll('#resumeList .fname')].map((n) => n.textContent),
  uploadMsg: document.getElementById('uploadMsg').textContent,
}))()`);
console.log('上传后:', JSON.stringify(after));

await evaluate("document.querySelector('.results-card')?.scrollIntoView({ block: 'start' })");
await sleep(400);
await evaluate("window.scrollTo(0, 0)");
await sleep(300);
const shot = await client.send('Page.captureScreenshot', { format: 'png' });
const { writeFile } = await import('node:fs/promises');
await writeFile('docs/upload-pdf.png', Buffer.from(shot.data, 'base64'));
console.log('已保存 docs/upload-pdf.png');

// 清理：只删除刚上传的那一份（按姓名定位），避免误删已有简历
const removed = await evaluate(`(() => {
  const items = [...document.querySelectorAll('#resumeList li')];
  const target = items.find((li) => li.querySelector('.fname')?.textContent.includes('赵磊'));
  if (!target) return false;
  target.querySelector('.del').click();
  return true;
})()`);
await sleep(2000);
const restored = await evaluate(`(() => ({
  resumes: document.getElementById('resumeCount').textContent,
  hint: document.getElementById('pendingHint').textContent,
}))()`);
console.log('删除后:', JSON.stringify(restored), '点击=', removed);

client.close();
process.exit(0);
