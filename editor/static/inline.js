(() => {
  'use strict';
  const contextDirectory = document.querySelector('meta[name="growth-content-directory"]')?.content;
  const parentURL = document.querySelector('meta[name="growth-parent-url"]')?.content || '/';
  let source = document.querySelector('meta[name="growth-article-path"]')?.content;
  let heading = source && document.querySelector('#single_header h1');
  let body = source && document.querySelector('.article-content');
  let token = '', authenticated = false, article = null, editor = null;
  let busy = false, uploading = 0, baseline = '', libraries = null, reloading = false;
  let creating = false, identifier = '', newFields = null, targetURL = location.pathname;
  const controls = document.createElement('div');
  controls.className = 'growth-editor-controls';
  controls.innerHTML = '<button type="button" data-action="new" hidden>新建文章</button><button type="button" data-action="account">管理员登录</button>';
  const account = controls.querySelector('[data-action="account"]');
  const newButton = controls.querySelector('[data-action="new"]');
  document.querySelector('#main-content')?.prepend(controls);
  const toolbar = document.createElement('div');
  toolbar.className = 'growth-editor-toolbar';
  toolbar.innerHTML = '<button type="button" data-action="edit" hidden>编辑这篇文章</button><button type="button" data-action="delete" hidden>删除文章</button><button type="button" data-action="cancel" hidden>取消</button><button type="button" data-action="save" hidden>保存到本地</button><span role="status" aria-live="polite"></span>';
  const buttons = Object.fromEntries([...toolbar.querySelectorAll('button')].map(button => [button.dataset.action, button]));
  const status = toolbar.querySelector('span');
  const titleInput = document.createElement('input');
  titleInput.className = 'growth-editor-title';
  titleInput.maxLength = 200;
  titleInput.setAttribute('aria-label', '文章标题');
  titleInput.hidden = true;
  const mount = document.createElement('div');
  mount.className = 'growth-editor-mount not-prose';
  mount.hidden = true;
  if (heading && body) {
    document.querySelector('#single_header').append(toolbar);
    heading.after(titleInput);
    body.before(mount);
  }
  const dialog = document.createElement('dialog');
  dialog.className = 'growth-editor-login';
  dialog.setAttribute('aria-label', '管理员登录');
  dialog.innerHTML = '<form><h2>管理员登录</h2><label>管理员密码<input type="password" autocomplete="current-password" maxlength="256" required></label><p role="status" aria-live="polite"></p><div><button type="button">取消</button><button type="submit">登录</button></div></form>';
  document.body.append(dialog);
  const passwordInput = dialog.querySelector('input');
  const loginStatus = dialog.querySelector('p');
  const loginSubmit = dialog.querySelector('[type="submit"]');
  async function refreshAuth() {
    const response = await fetch('/api/config', {cache: 'no-store'});
    const config = await response.json();
    if (!response.ok) throw new Error(config.error || '无法读取登录状态');
    token = config.token;
    authenticated = config.authenticated;
    updateControls();
    return config;
  }
  async function api(url, data) {
    const options = {cache: 'no-store'};
    if (data !== undefined) {
      options.method = 'POST';
      options.headers = {'Content-Type': 'application/json', 'X-Editor-Token': token};
      options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 401) await refreshAuth();
      throw new Error(result.error || '操作失败');
    }
    return result;
  }
  function updateControls() {
    account.textContent = authenticated ? '退出登录' : '管理员登录';
    account.disabled = busy || uploading > 0;
    newButton.hidden = !authenticated || !!editor || contextDirectory === undefined;
    newButton.disabled = busy || uploading > 0;
    buttons.edit.hidden = !authenticated || !!editor || !article?.editable;
    buttons.delete.hidden = !authenticated || !!editor || !article || article.kind !== '文章';
    ['cancel', 'save'].forEach(name => {buttons[name].hidden = !editor;});
    Object.values(buttons).forEach(button => {button.disabled = busy || uploading > 0;});
    buttons.save.disabled ||= !authenticated;
    if (editor) {
      mount.inert = busy;
      titleInput.disabled = busy;
      if (newFields) newFields.inert = busy;
    }
  }
  const dirty = () => !!editor && (creating || titleInput.value !== article.title || editor.getMarkdown() !== baseline);
  function cancel() {
    if (busy || uploading || (dirty() && !confirm('还有未保存的修改，确定放弃吗？'))) return false;
    if (editor) editor.destroy();
    editor = null;
    if (creating) {creating = false; reloading = true; location.reload(); return false;}
    mount.replaceChildren();
    mount.hidden = true;
    titleInput.hidden = true;
    if (heading) heading.hidden = false;
    if (body) body.hidden = false;
    document.querySelector('.toc')?.classList.remove('growth-editor-hidden');
    updateControls();
    return true;
  }
  function loadLibraries() {
    if (libraries) return libraries;
    libraries = (async () => {
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = '/vendor/toastui-editor.min.css'; document.head.append(css);
      for (const url of ['/vendor/toastui-editor-all.min.js', '/vendor/zh-cn.js']) {
        await new Promise((resolve, reject) => {
          const script = document.createElement('script'); script.src = url;
          script.onload = resolve; script.onerror = () => reject(new Error('编辑器组件加载失败，请刷新后重试。'));
          document.head.append(script);
        });
      }
    })();
    libraries.catch(() => {libraries = null;});
    return libraries;
  }
  async function upload(blob, callback) {
    uploading++; updateControls(); status.textContent = '正在上传图片…';
    try {
      if (blob.size > 8 * 1024 * 1024) throw new Error('图片不能超过 8 MB');
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let binary = '';
      for (let offset = 0; offset < bytes.length; offset += 16384) binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
      const result = await api(creating ? '/api/upload-new' : '/api/upload', {path: article?.path, data: btoa(binary)});
      callback(result.url, blob.name || '图片');
      status.textContent = '图片已插入，请保存文章。';
    } catch (error) {status.textContent = error.message;}
    finally {uploading--; updateControls();}
  }
  async function edit() {
    if (!authenticated || !article?.editable || editor || busy) return;
    busy = true; updateControls(); status.textContent = '正在打开编辑…';
    try {
      article = (await api('/api/article?path=' + encodeURIComponent(source))).article;
      if (!article.editable) throw new Error('此页包含专用图表组件，暂时不能编辑。');
      await loadLibraries();
      titleInput.value = article.title;
      heading.hidden = true; titleInput.hidden = false; body.hidden = true; mount.hidden = false;
      document.querySelector('.toc')?.classList.add('growth-editor-hidden');
      editor = new toastui.Editor({el: mount, height: 'auto', minHeight: '500px', initialEditType: 'wysiwyg',
        hideModeSwitch: true, language: 'zh-CN', initialValue: article.body, usageStatistics: false,
        toolbarItems: [['heading','bold','italic','strike'],['hr','quote'],['ul','ol','task','indent','outdent'],['table','image','link'],['code','codeblock']],
        hooks: {addImageBlobHook: upload}});
      baseline = editor.getMarkdown();
      status.textContent = '直接修改正文，保存后恢复网站排版。';
    } catch (error) {
      status.textContent = error.message;
      if (!editor) {heading.hidden = false; titleInput.hidden = true; body.hidden = false; mount.hidden = true;}
    }
    finally {busy = false; updateControls();}
  }
  async function startNew() {
    if (!authenticated || editor || busy || contextDirectory === undefined) return;
    busy = true; updateControls();
    try {
      await loadLibraries();
      const main = document.querySelector('#main-content');
      const original = document.createElement('div');
      [...main.children].filter(child => child !== controls).forEach(child => original.append(child));
      original.hidden = true; main.append(original);
      const panel = document.createElement('section'); panel.className = 'growth-editor-compose';
      panel.innerHTML = '<h1>新建文章</h1><p>写好后保存到本地 Markdown。</p>';
      newFields = document.createElement('div'); newFields.className = 'growth-editor-new-fields';
      const isQuote = contextDirectory.split('/')[0] === 'quotes';
      const isBook = /^reading\/books(?:\/|$)/.test(contextDirectory);
      const isLog = /^reading\/logs(?:\/|$)/.test(contextDirectory);
      const destination = document.createElement('p'); destination.className = 'growth-editor-destination';
      destination.textContent = '保存位置：content/' + (contextDirectory ? contextDirectory + '/' : ''); panel.append(destination);
      newFields.innerHTML = '<label>日期<input type="date" name="date" required></label>';
      if (isQuote) newFields.insertAdjacentHTML('beforeend', '<div class="growth-editor-quote-fields"><label>金句原文<textarea name="quote" rows="3" maxlength="2000" required></textarea></label><label>作者<input name="author" maxlength="2000"></label><label>出处<input name="work" maxlength="2000"></label><label>类型<select name="kind"><option>名言</option><option>诗词</option><option>电影台词</option></select></label><p>原文和出处会自动加入正文，下面可以写感想。</p></div>');
      if (isBook) newFields.insertAdjacentHTML('beforeend', '<label>作者<input name="author" maxlength="200"></label><label>阅读状态<select name="status"><option>在读</option><option>未读</option><option>已读</option></select></label>');
      if (isLog) newFields.insertAdjacentHTML('beforeend', '<label>书籍 book_id<input name="book_id" required></label><label>阅读分钟<input name="reading_minutes" type="number" min="0" step="1" required></label><label>页数<input name="pages" type="number" min="0" step="1" value="0" required></label>');
      const parts = Object.fromEntries(new Intl.DateTimeFormat('en', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).map(part => [part.type,part.value]));
      const today = parts.year + '-' + parts.month + '-' + parts.day;
      const day = newFields.querySelector('[name="date"]'); day.value = today; day.max = today;
      titleInput.value = ''; titleInput.placeholder = '输入文章标题'; titleInput.hidden = false;
      mount.hidden = false; panel.append(newFields, titleInput, toolbar, mount); main.append(panel);
      heading = panel.querySelector('h1'); body = document.createElement('div');
      identifier = crypto.randomUUID().replaceAll('-', ''); creating = true;
      editor = new toastui.Editor({el:mount,height:'auto',minHeight:'500px',initialEditType:'wysiwyg',
        hideModeSwitch:true,language:'zh-CN',initialValue:'',usageStatistics:false,
        toolbarItems:[['heading','bold','italic','strike'],['hr','quote'],['ul','ol','task','indent','outdent'],['table','image','link'],['code','codeblock']],
        hooks:{addImageBlobHook:upload}});
      baseline = editor.getMarkdown(); status.textContent = '开始写正文；保存前不会创建空文章。'; titleInput.focus();
    } catch (error) {status.textContent = error.message;}
    finally {busy = false; updateControls();}
  }
  async function reloadRendered(message) {
    // Wait for Hugo's actual build, so title, table of contents and body update together.
    for (let attempt = 0; attempt < 20; attempt++) {
      const response = await fetch(targetURL, {cache: 'no-store'});
      const document_ = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (document_.querySelector('meta[name="growth-article-revision"]')?.content === article.revision) {
        sessionStorage.setItem('growth-editor-message', JSON.stringify({path: targetURL, message}));
        reloading = true;
        location.assign(targetURL + location.hash); return;
      }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    status.textContent = message + ' 预览仍在更新，请稍后刷新。';
  }
  async function save() {
    if (!authenticated || !editor || busy || uploading) return;
    if (creating && [...newFields.querySelectorAll('[required]')].some(field => !field.reportValidity())) return;
    if (!dirty()) {cancel(); status.textContent = '没有修改，文件保持原样。'; return;}
    busy = true; updateControls();
    let saved = false, message = '';
    try {
      if (dirty()) {
        status.textContent = '正在保存 Markdown…';
        if (creating) {
          const value = name => newFields.querySelector('[name="' + name + '"]')?.value || '';
          const result = await api('/api/create', {directory:contextDirectory,date:value('date'),title:titleInput.value,
            body:editor.getMarkdown(),identifier,quote_fields:{quote:value('quote'),author:value('author'),work:value('work'),kind:value('kind')},reading_fields:{author:value('author'),status:value('status'),book_id:value('book_id'),reading_minutes:value('reading_minutes'),pages:value('pages')}});
          article = result.article; targetURL = result.url; source = article.path; creating = false;
          newFields.hidden = true;
        } else {
          article = (await api('/api/save', {path: article.path, title: titleInput.value,
            body: editor.getMarkdown(), revision: article.revision})).article;
        }
        baseline = editor.getMarkdown(); titleInput.value = article.title; saved = true;
      }
      message = '已保存到本地。';
      await reloadRendered(message);
    } catch (error) {
      message = (saved ? '文章已保存，但后续操作未完成：' : '') + error.message;
      status.textContent = message;
      if (saved) {try {await reloadRendered(message);} catch (_) {}}
    } finally {busy = false; updateControls();}
  }
  async function removeArticle() {
    if (!authenticated || !article || editor || busy || uploading) return;
    if (!confirm('删除本地文章“' + article.title + '”？图片会保留。已有提交可通过 Git 恢复，未提交的新文章删除后无法恢复。')) return;
    busy = true; updateControls(); status.textContent = '正在删除本地文章…';
    try {
      await api('/api/delete', {path: article.path, revision: article.revision, url: location.pathname});
      status.textContent = '本地文件已删除，正在更新栏目…';
      for (let attempt = 0; attempt < 20; attempt++) {
        const response = await fetch(location.pathname, {cache:'no-store'});
        await response.text();
        if (response.status === 404) break;
        await new Promise(resolve => setTimeout(resolve, 250));
      }
      reloading = true; location.assign(parentURL);
    } catch (error) {status.textContent = error.message;}
    finally {busy = false; updateControls();}
  }
  account.addEventListener('click', async () => {
    if (busy || uploading) return;
    if (authenticated) {
      if (!cancel()) return;
      try {await api('/api/logout', {}); await refreshAuth(); status.textContent = '已退出登录。';}
      catch (error) {status.textContent = error.message;}
      return;
    }
    try {
      const config = await refreshAuth();
      loginStatus.textContent = config.configured ? '' : '请先运行 setup-editor.cmd 设置管理员密码。';
      loginSubmit.disabled = !config.configured; dialog.showModal(); passwordInput.focus();
    } catch (error) {status.textContent = error.message;}
  });
  dialog.querySelector('[type="button"]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {passwordInput.value = '';});
  dialog.querySelector('form').addEventListener('submit', async event => {
    event.preventDefault(); loginSubmit.disabled = true; loginStatus.textContent = '正在登录…';
    const password = passwordInput.value; passwordInput.value = '';
    try {
      const result = await api('/api/login', {password}); token = result.token; authenticated = true;
      updateControls(); dialog.close(); status.textContent = '已登录。';
    } catch (error) {loginStatus.textContent = error.message;}
    finally {loginSubmit.disabled = false;}
  });
  buttons.edit.addEventListener('click', edit);
  buttons.delete.addEventListener('click', removeArticle);
  newButton.addEventListener('click', startNew);
  buttons.cancel.addEventListener('click', () => {if (cancel()) status.textContent = '';});
  buttons.save.addEventListener('click', () => save());
  window.addEventListener('beforeunload', event => {
    if (!reloading && (dirty() || busy || uploading)) {event.preventDefault(); event.returnValue = '';}
  });
  (async () => {
    try {
      await refreshAuth();
      if (source && heading && body) article = (await api('/api/article?path=' + encodeURIComponent(source))).article;
      updateControls();
      if (authenticated && article && !article.editable) status.textContent = '此页包含专用图表组件，可阅读，暂时不能编辑。';
      const stored = sessionStorage.getItem('growth-editor-message');
      if (stored) {
        sessionStorage.removeItem('growth-editor-message');
        const message = JSON.parse(stored);
        if (message.path === location.pathname) status.textContent = message.message;
      }
    } catch (error) {status.textContent = error.message;}
  })();
})();
