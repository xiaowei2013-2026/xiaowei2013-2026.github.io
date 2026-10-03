(() => {
  const ns = 'http://www.w3.org/2000/svg';
  const dateFormatter = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  function timestamp(value) {
    const match = String(value).trim().match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::00)?(?:\+08:00)?$/);
    if (!match) throw new Error('时间请使用 YYYY-MM-DD HH:mm，例如 2026-10-03 09:30。');
    const [, y, mo, d, h, mi] = match;
    const ms = Date.parse(`${y}-${mo}-${d}T${h}:${mi}:00+08:00`);
    if (!Number.isFinite(ms) || dateFormatter.format(new Date(ms)) !== `${y}-${mo}-${d} ${h}:${mi}`) throw new Error('日期或时间无效。');
    return ms;
  }
  function normalize(items) {
    if (!Array.isArray(items)) throw new Error('记录必须为数组。');
    return items.map((item, i) => {
      try {
        const ms = timestamp(item.time);
        const speed = Number(item.speed);
        const content = String(item.content ?? '').trim();
        if (item.speed === '' || item.speed == null || !Number.isFinite(speed) || speed < 0) throw new Error('速度必须是大于等于 0 的数字。');
        if (!content) throw new Error('请填写练习内容。');
        return { time: dateFormatter.format(new Date(ms)), speed, content, ms };
      } catch (error) { throw new Error(`第 ${i + 1} 条：${error.message}`); }
    }).sort((a, b) => a.ms - b.ms);
  }
  // CSV parser supports quoted commas, escaped quotes and multiline content.
  function csv(text) {
    const rows = []; let row = [], field = '', quoted = false;
    text = text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c === '"') {
        if (quoted && text[i + 1] === '"') { field += '"'; i++; }
        else quoted = !quoted;
      } else if (!quoted && (c === ',' || c === '\n')) {
        row.push(field); field = '';
        if (c === '\n') { if (row.some(v => v.trim())) rows.push(row); row = []; }
      } else field += c;
    }
    if (quoted) throw new Error('CSV 引号未闭合。');
    row.push(field); if (row.some(v => v.trim())) rows.push(row);
    const header = rows.shift()?.map(v => v.trim());
    if (!header || header.join(',') !== '时间,速度,内容') throw new Error('CSV 首行必须为：时间,速度,内容。请使用 UTF-8 编码。');
    return rows.map((values, i) => {
      if (values.length !== 3) throw new Error(`CSV 第 ${i + 2} 行需要三列；包含逗号的内容请用双引号包围。`);
      return { time: values[0], speed: values[1].trim(), content: values[2] };
    });
  }
  document.querySelectorAll('.typing-chart').forEach(root => {
    const svg = root.querySelector('[data-plot]'), status = root.querySelector('[data-status]'), detail = root.querySelector('[data-detail]');
    const rows = root.querySelector('[data-rows]'), exportButton = root.querySelector('[data-export]');
    let records = [];
    function element(tag, attrs = {}, text) {
      const node = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
      if (text != null) node.textContent = text;
      svg.append(node); return node;
    }
    function render() {
      svg.replaceChildren(); rows.replaceChildren(); exportButton.disabled = !records.length;
      detail.textContent = '选择一个数据点查看详情。';
      if (!records.length) { element('text', { x: 450, y: 160, 'text-anchor': 'middle' }, '还没有练习记录，请导入 CSV。'); return; }
      const left = 70, right = 870, top = 30, bottom = 270;
      let min = records[0].ms, max = records.at(-1).ms;
      if (min === max) { min -= 60000; max += 60000; }
      const ceiling = Math.max(10, Math.ceil(Math.max(...records.map(r => r.speed)) / 10) * 10);
      const x = ms => left + (ms - min) / (max - min) * (right - left);
      const y = speed => bottom - speed / ceiling * (bottom - top);
      for (let i = 0; i <= 5; i++) {
        const speed = ceiling * i / 5;
        element('line', { x1: left, x2: right, y1: y(speed), y2: y(speed), class: 'chart-grid' });
        element('text', { x: left - 12, y: y(speed) + 4, 'text-anchor': 'end' }, Number(speed.toFixed(1)));
      }
      element('text', { x: left, y: 16 }, '速度（字/分钟）');
      element('text', { x: 470, y: 350, 'text-anchor': 'middle' }, '练习时间（北京时间，精确到分钟）');
      for (let i = 0; i <= 4; i++) {
        const ms = min + (max - min) * i / 4;
        const label = dateFormatter.format(new Date(ms));
        element('text', { x: x(ms), y: 298, 'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle' }, label.slice(0, 10));
        element('text', { x: x(ms), y: 315, 'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle' }, label.slice(11));
      }
      element('polyline', { points: records.map(r => `${x(r.ms)},${y(r.speed)}`).join(' '), class: 'chart-line' });
      records.forEach(record => {
        const text = `${record.time}｜${record.speed} 字/分钟｜${record.content}`;
        const point = element('circle', { cx: x(record.ms), cy: y(record.speed), r: 6, class: 'chart-dot', tabindex: 0, role: 'button', 'aria-label': text });
        const title = document.createElementNS(ns, 'title'); title.textContent = text; point.append(title);
        ['mouseenter', 'focus', 'click'].forEach(event => point.addEventListener(event, () => { detail.textContent = text; }));
        point.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); detail.textContent = text; } });
        const tr = document.createElement('tr');
        [record.time, record.speed, record.content].forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
        rows.append(tr);
      });
    }
    try { records = normalize(JSON.parse(root.querySelector('[data-records]').textContent)); render(); status.textContent = `共 ${records.length} 次练习。`; }
    catch (error) { status.textContent = error.message; }
    root.querySelector('[data-import]').addEventListener('change', async event => {
      const file = event.target.files[0]; if (!file) return;
      try { const imported = normalize(csv(await file.text())); records = imported; render(); status.textContent = `已预览 ${records.length} 次练习（替换当前预览），尚未保存到网站。`; }
      catch (error) { status.textContent = `导入失败：${error.message}`; }
      event.target.value = '';
    });
    exportButton.addEventListener('click', () => {
      const data = records.map(({ time, speed, content }) => ({ time, speed, content }));
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = 'typing_records.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  });
})();
