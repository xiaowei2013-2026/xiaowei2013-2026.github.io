(() => {
  const ns = 'http://www.w3.org/2000/svg';
  const formatter = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  function normalize(items) {
    if (!Array.isArray(items)) throw new Error('记录必须为数组。');
    return items.map((item, i) => {
      try {
        const match = String(item?.time ?? '').match(/^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?$/);
        if (!match) throw new Error('时间请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:mm。');
        const canonical = `${match[1]} ${match[2] ?? '00:00'}`;
        const ms = Date.parse(`${canonical.replace(' ', 'T')}:00+08:00`);
        if (!Number.isFinite(ms) || formatter.format(new Date(ms)) !== canonical) throw new Error('日期或时间无效。');
        if (typeof item.weight !== 'number' || !Number.isFinite(item.weight) || item.weight <= 0) throw new Error('体重必须是大于 0 的数字，JSON 中的单位为公斤。');
        // Store kilograms in JSON; render all chart values in jin (1 kg = 2 jin).
        return { time: match[2] ? canonical : match[1], weight: Number((item.weight * 2).toPrecision(15)), ms };
      } catch (error) { throw new Error(`第 ${i + 1} 条：${error.message}`); }
    }).sort((a, b) => a.ms - b.ms);
  }
  document.querySelectorAll('.weight-chart').forEach(root => {
    const svg = root.querySelector('[data-plot]'), status = root.querySelector('[data-status]'), detail = root.querySelector('[data-detail]'), rows = root.querySelector('[data-rows]');
    let records;
    function element(tag, attrs, text) {
      const node = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
      if (text != null) node.textContent = text;
      svg.append(node); return node;
    }
    function render() {
      const width = Math.max(240, svg.clientWidth);
      svg.setAttribute('viewBox', `0 0 ${width} 360`);
      svg.replaceChildren(); rows.replaceChildren();
      detail.textContent = records.length ? '选择一个数据点查看详情。' : '';
      if (!records.length) { element('text', { x: width / 2, y: 160, 'text-anchor': 'middle' }, '还没有体重记录。'); return; }
      const left = 52, right = width - 16, top = 32, bottom = 270;
      let minTime = records[0].ms, maxTime = records.at(-1).ms;
      if (minTime === maxTime) { minTime -= 86400000; maxTime += 86400000; }
      const weights = records.map(r => r.weight);
      const low = Math.min(...weights), high = Math.max(...weights);
      const padding = Math.max(1, (high - low) * .15);
      const floor = Math.max(0, Math.floor(low - padding)), ceiling = Math.ceil(high + padding);
      const x = ms => left + (ms - minTime) / (maxTime - minTime) * (right - left);
      const y = weight => bottom - (weight - floor) / (ceiling - floor) * (bottom - top);
      for (let i = 0; i <= 5; i++) {
        const value = floor + (ceiling - floor) * i / 5;
        element('line', { x1: left, x2: right, y1: y(value), y2: y(value), class: 'chart-grid' });
        element('text', { x: left - 8, y: y(value) + 4, 'text-anchor': 'end' }, Number(value.toFixed(1)));
      }
      element('text', { x: left, y: 16 }, '体重（斤）');
      element('text', { x: width / 2, y: 350, 'text-anchor': 'middle' }, '测量时间（北京时间）');
      const intervals = width < 360 ? 1 : width < 600 ? 2 : 4;
      for (let i = 0; i <= intervals; i++) {
        const ms = minTime + (maxTime - minTime) * i / intervals;
        const label = formatter.format(new Date(ms));
        const anchor = i === 0 ? 'start' : i === intervals ? 'end' : 'middle';
        element('text', { x: x(ms), y: 298, 'text-anchor': anchor }, label.slice(0, 10));
        element('text', { x: x(ms), y: 315, 'text-anchor': anchor }, label.slice(11));
      }
      element('polyline', { points: records.map(r => `${x(r.ms)},${y(r.weight)}`).join(' '), class: 'chart-line' });
      records.forEach(record => {
        const text = `${record.time}｜${record.weight} 斤`;
        const point = element('circle', { cx: x(record.ms), cy: y(record.weight), r: 5, class: 'chart-dot', tabindex: 0, role: 'button', 'aria-label': text });
        const title = document.createElementNS(ns, 'title'); title.textContent = text; point.append(title);
        ['mouseenter', 'focus', 'click'].forEach(event => point.addEventListener(event, () => { detail.textContent = text; }));
        point.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); detail.textContent = text; } });
        const tr = document.createElement('tr');
        [record.time, record.weight].forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
        rows.append(tr);
      });
    }
    try { records = normalize(JSON.parse(root.querySelector('[data-records]').textContent)); }
    catch (error) { status.textContent = error.message; return; }
    status.textContent = `共 ${records.length} 条记录。`;
    render();
    let lastWidth = svg.clientWidth;
    new ResizeObserver(() => { if (lastWidth !== svg.clientWidth) { lastWidth = svg.clientWidth; render(); } }).observe(svg);
  });
})();
