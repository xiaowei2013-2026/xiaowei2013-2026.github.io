(() => {
  'use strict';
  let source = document.querySelector('meta[name="growth-article-path"]')?.content;
  let heading = source && document.querySelector('#single_header h1');
  let body = source && document.querySelector('.article-content');
  let token = '', authenticated = false, article = null, editor = null;
  let busy = false, uploading = 0, baseline = '', libraries = null, reloading = false;
  let creating = false, identifier = '', newFields = null, targetURL = location.pathname;
  const controls = document.createElement('div');
  controls.className = 'growth-editor-controls';
  controls.innerHTML = '<button type="button" data-action="new" hidden>新建文章</button><button type="button" data-action="sync-all" hidden>同步到 GitHub</button><button type="button" data-action="trash" hidden>回收站</button><button type="button" data-action="account">管理员登录</button>';
  const account = controls.querySelector('[data-action="account"]');
  const newButton = controls.querySelector('[data-action="new"]');
  const trashButton = controls.querySelector('[data-action="trash"]');
  const syncButton = controls.querySelector('[data-action="sync-all"]');
  document.querySelector('#main-content')?.prepend(controls);
  const toolbar = document.createElement('div');
  toolbar.className = 'growth-editor-toolbar';
  toolbar.innerHTML = '<button type="button" data-action="edit" hidden>编辑这篇文章</button><button type="button" data-action="publish" hidden>发布到 GitHub</button><button type="button" data-action="delete" hidden>删除文章</button><button type="button" data-action="cancel" hidden>取消</button><button type="button" data-action="save" hidden>保存到本地</button><button type="button" data-action="save-publish" hidden>保存并发布</button><span role="status" aria-live="polite"></span>';
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
  const trashDialog = document.createElement('dialog');
  trashDialog.className = 'growth-editor-login growth-editor-trash';
  trashDialog.setAttribute('aria-label', '文章回收站');
  trashDialog.innerHTML = '<h2>文章回收站</h2><p>本地删除可恢复。发布删除后，GitHub 构建成功才会从线上移除。</p><p class="growth-trash-status" role="status" aria-live="polite"></p><div class="growth-trash-items"></div><button type="button">关闭</button>';
  document.body.append(trashDialog);
  const trashStatus = trashDialog.querySelector('.growth-trash-status');
  trashDialog.querySelector('button').addEventListener('click', () => {if (!busy) trashDialog.close();});
  trashDialog.addEventListener('cancel', event => {if (busy) event.preventDefault();});
  const syncDialog = document.createElement('dialog');
  syncDialog.className = 'growth-editor-login growth-editor-trash';
  syncDialog.setAttribute('aria-label', '文章与图片同步');
  syncDialog.innerHTML = '<h2>文章与图片同步</h2><p>同步下方清单中的新增、修改和删除。同步时会核对 GitHub 最新版本。</p><p class="growth-sync-summary"></p><p class="growth-sync-status" role="status" aria-live="polite"></p><div class="growth-sync-items"></div><div class="growth-sync-actions"><button type="button" data-sync="refresh">刷新清单</button><button type="button" data-sync="publish" disabled>同步清单中的全部改动</button><button type="button" data-sync="close">关闭</button></div>';
  document.body.append(syncDialog);
  const syncStatus = syncDialog.querySelector('.growth-sync-status');
  const syncPublish = syncDialog.querySelector('[data-sync="publish"]');
  let syncPlan = null;
  syncDialog.querySelector('[data-sync="close"]').addEventListener('click', () => {if (!busy) syncDialog.close();});
  syncDialog.addEventListener('cancel', event => {if (busy) event.preventDefault();});

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
    newButton.hidden = !authenticated || !!editor;
    newButton.disabled = busy || uploading > 0;
    trashButton.hidden = !authenticated || !!editor;
    trashButton.disabled = busy || uploading > 0;
    syncButton.hidden = !authenticated || !!editor;
    syncButton.disabled = busy || uploading > 0;
    buttons.edit.hidden = !authenticated || !!editor || !article?.editable;
    buttons.publish.hidden = !authenticated || !!editor || !article;
    buttons.delete.hidden = !authenticated || !!editor || !article || article.kind !== '文章';
    ['cancel', 'save', 'save-publish'].forEach(name => {buttons[name].hidden = !editor;});
    Object.values(buttons).forEach(button => {button.disabled = busy || uploading > 0;});
    buttons.save.disabled ||= !authenticated;
    buttons['save-publish'].disabled ||= !authenticated;
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
    if (!authenticated || editor || busy) return;
    busy = true; updateControls();
    try {
      await loadLibraries();
      const main = document.querySelector('#main-content');
      const original = document.createElement('div');
      [...main.children].filter(child => child !== controls).forEach(child => original.append(child));
      original.hidden = true; main.append(original);
      const panel = document.createElement('section'); panel.className = 'growth-editor-compose';
      panel.innerHTML = '<h1>新建文章</h1><p>写好后保存为 Markdown，点击“保存并发布”同步到 GitHub。</p>';
      newFields = document.createElement('div'); newFields.className = 'growth-editor-new-fields';
      newFields.innerHTML = '<label>分类<select name="module"><option value="diary">日记</option><option value="english">英语笔记</option><option value="reading">阅读文章</option><option value="other">其他文章</option><option value="quotes">每日金句</option></select></label><label>日期<input type="date" name="date" required></label><div class="growth-editor-quote-fields" hidden><label>金句原文<textarea name="quote" rows="3" maxlength="2000"></textarea></label><label>作者<input name="author" maxlength="2000"></label><label>出处<input name="work" maxlength="2000"></label><label>类型<select name="kind"><option>名言</option><option>诗词</option><option>电影台词</option></select></label><p>金句原文和出处会自动加入正文，下面可以写感想。</p></div>';
      const parts = Object.fromEntries(new Intl.DateTimeFormat('en', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).map(part => [part.type,part.value]));
      const today = parts.year + '-' + parts.month + '-' + parts.day;
      const day = newFields.querySelector('[name="date"]'); day.value = today; day.max = today;
      if (source?.startsWith('english/')) newFields.querySelector('[name="module"]').value = 'english';
      else if (source?.startsWith('reading/')) newFields.querySelector('[name="module"]').value = 'reading';
      else if (source?.startsWith('other/')) newFields.querySelector('[name="module"]').value = 'other';
      const toggleQuote = () => {
        const quoted = newFields.querySelector('[name="module"]').value === 'quotes';
        newFields.querySelector('.growth-editor-quote-fields').hidden = !quoted;
        newFields.querySelector('[name="quote"]').required = quoted;
      };
      newFields.querySelector('[name="module"]').addEventListener('change', toggleQuote); toggleQuote();
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
  async function save(publish = false) {
    if (!authenticated || !editor || busy || uploading) return;
    if (creating && [...newFields.querySelectorAll('[required]')].some(field => !field.reportValidity())) return;
    if (!dirty() && !publish) {cancel(); status.textContent = '没有修改，文件保持原样。'; return;}
    busy = true; updateControls();
    let saved = false, message = '';
    try {
      if (dirty()) {
        status.textContent = '正在保存 Markdown…';
        if (creating) {
          const value = name => newFields.querySelector('[name="' + name + '"]').value;
          const result = await api('/api/create', {module:value('module'),date:value('date'),title:titleInput.value,
            body:editor.getMarkdown(),identifier,quote_fields:{quote:value('quote'),author:value('author'),work:value('work'),kind:value('kind')}});
          article = result.article; targetURL = result.url; source = article.path; creating = false;
          newFields.hidden = true;
        } else {
          article = (await api('/api/save', {path: article.path, title: titleInput.value,
            body: editor.getMarkdown(), revision: article.revision})).article;
        }
        baseline = editor.getMarkdown(); titleInput.value = article.title; saved = true;
      }
      message = '已保存到本地，尚未发布到 GitHub。';
      if (publish) {
        status.textContent = '正在发布到 GitHub…';
        const result = await api('/api/sync', {path: article.path, revision: article.revision});
        message = result.changed ? '已同步到 GitHub，等待网站构建部署完成。' : '内容已与 GitHub 一致。';
      }
      await reloadRendered(message);
    } catch (error) {
      message = (saved ? '文章已保存，但后续操作未完成：' : '') + error.message;
      status.textContent = message;
      if (saved) {try {await reloadRendered(message);} catch (_) {}}
    } finally {busy = false; updateControls();}
  }
  async function publish() {
    if (!authenticated || !article || editor || busy) return;
    busy = true; updateControls(); status.textContent = '正在发布到 GitHub…';
    try {
      const result = await api('/api/sync', {path: article.path, revision: article.revision});
      status.textContent = result.changed ? '已同步到 GitHub，等待网站构建部署完成。' : '内容已与 GitHub 一致。';
    } catch (error) {status.textContent = error.message;}
    finally {busy = false; updateControls();}
  }
  async function removeArticle() {
    if (!authenticated || !article || editor || busy || uploading) return;
    if (!confirm('将“' + article.title + '”移入本地回收站？图片会保留，GitHub 暂不改变。')) return;
    busy = true; updateControls(); status.textContent = '正在移入回收站…';
    try {
      await api('/api/delete', {path: article.path, revision: article.revision, url: location.pathname});
      reloading = true; location.assign('/#recycle');
    } catch (error) {status.textContent = error.message;}
    finally {busy = false; updateControls();}
  }
  async function renderTrash() {
    const result = await api('/api/trash');
    const list = trashDialog.querySelector('.growth-trash-items'); list.replaceChildren();
    if (!result.items.length) {const text = document.createElement('p'); text.textContent = '回收站为空。'; list.append(text);}
    result.items.forEach(item => {
      const row = document.createElement('div'); row.className = 'growth-trash-row';
      const title = document.createElement('strong'); title.textContent = item.title;
      const info = document.createElement('small'); info.textContent = new Date(item.deleted_at).toLocaleString() + ' · ' + (item.github_deleted ? '已发布删除' : '尚未发布删除');
      const actions = document.createElement('div');
      for (const [label, route] of [['恢复到本地', '/api/restore'], ['发布删除到 GitHub', '/api/sync-delete']]) {
        if (route === '/api/sync-delete' && item.github_deleted) continue;
        const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
        button.addEventListener('click', async () => {
          if (busy) return;
          if (route === '/api/sync-delete' && !confirm('确认向 GitHub 发布“' + item.title + '”的删除？')) return;
          busy = true; updateControls(); trashDialog.querySelectorAll('button').forEach(element => {element.disabled = true;});
          trashStatus.textContent = route === '/api/restore' ? '正在恢复…' : '正在发布删除…';
          try {
            const result = await api(route, {id: item.id});
            trashStatus.textContent = route === '/api/restore' ? '已恢复到本地。若之前发布过删除，请打开文章重新发布。' : (result.changed ? '删除已同步到 GitHub，等待网站构建完成。' : 'GitHub 中已无这篇文章，无需新提交。');
            await renderTrash();
            if (route === '/api/restore' && result.item.url?.startsWith('/') && !result.item.url.startsWith('//')) {
              for (let attempt = 0; attempt < 20; attempt++) {
                const response = await fetch(result.item.url, {cache:'no-store'});
                const rendered = new DOMParser().parseFromString(await response.text(), 'text/html');
                if (rendered.querySelector('meta[name="growth-article-revision"]')?.content === result.item.revision) {
                  reloading = true; location.assign(result.item.url); break;
                }
                await new Promise(resolve => setTimeout(resolve, 250));
              }
            }
          } catch (error) {trashStatus.textContent = error.message;}
          finally {busy = false; updateControls(); trashDialog.querySelectorAll('button').forEach(element => {element.disabled = false;});}
        });
        actions.append(button);
      }
      row.append(title, info, actions); list.append(row);
    });
  }
  async function openTrash() {
    if (!authenticated || editor || busy) return;
    trashStatus.textContent = '';
    trashDialog.showModal();
    try {await renderTrash();} catch (error) {trashStatus.textContent = error.message;}
  }
  async function renderSync() {
    syncPlan = null; syncPublish.disabled = true;
    const plan = await api('/api/sync-plan'); syncPlan = plan;
    const list = syncDialog.querySelector('.growth-sync-items'); list.replaceChildren();
    const labels = {A:'新增', M:'修改', D:'删除', T:'类型变化'};
    plan.changes.forEach(item => {
      const row = document.createElement('p'); row.className = 'growth-sync-file';
      row.textContent = (labels[item.action] || '修改') + ' · ' + item.path; list.append(row);
    });
    const summary = syncDialog.querySelector('.growth-sync-summary');
    summary.textContent = plan.changes.length + ' 个待同步文件。' + (plan.other_changes ? ' 另有 ' + plan.other_changes + ' 个范围外文件改动，本次不包含。' : '');
    syncPublish.textContent = plan.retry ? '重试上次同步' : '同步清单中的全部改动';
    syncPublish.disabled = !!plan.blocked || (!plan.changes.length && !plan.retry);
    if (plan.blocked) syncStatus.textContent = plan.blocked;
    else if (!plan.changes.length && !plan.retry) syncStatus.textContent = '文章与图片已与最近获取的 GitHub 版本一致。';
  }
  async function openSync() {
    if (!authenticated || editor || busy) return;
    syncStatus.textContent = '正在读取同步清单…'; syncDialog.showModal();
    try {await renderSync(); if (syncPlan.changes.length && !syncPlan.blocked) syncStatus.textContent = '请检查清单，然后点击同步。';}
    catch (error) {syncStatus.textContent = error.message;}
  }
  syncDialog.querySelector('[data-sync="refresh"]').addEventListener('click', async () => {
    if (busy) return; syncStatus.textContent = '正在刷新清单…';
    try {await renderSync(); if (syncPlan.changes.length && !syncPlan.blocked) syncStatus.textContent = '清单已刷新。';}
    catch (error) {syncStatus.textContent = error.message;}
  });
  syncPublish.addEventListener('click', async () => {
    if (busy || !syncPlan || syncPublish.disabled) return;
    busy = true; updateControls(); syncDialog.querySelectorAll('button').forEach(button => {button.disabled = true;});
    syncStatus.textContent = '正在提交并同步到 GitHub…';
    try {
      const result = await api('/api/sync-batch', {scope:'content',revision:syncPlan.revision});
      await renderSync(); syncStatus.textContent = result.changed ? '清单已同步到 GitHub，等待网站构建部署完成。' : '内容已与 GitHub 一致，无需新提交。';
    } catch (error) {syncStatus.textContent = error.message;syncPublish.disabled = false;}
    finally {
      busy = false; updateControls();
      syncDialog.querySelector('[data-sync="refresh"]').disabled = false;
      syncDialog.querySelector('[data-sync="close"]').disabled = false;
    }
  });
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
  trashButton.addEventListener('click', openTrash);
  syncButton.addEventListener('click', openSync);
  newButton.addEventListener('click', startNew);
  buttons.cancel.addEventListener('click', () => {if (cancel()) status.textContent = '';});
  buttons.save.addEventListener('click', () => save());
  buttons['save-publish'].addEventListener('click', () => save(true));
  buttons.publish.addEventListener('click', publish);
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
      if (location.hash === '#recycle' && authenticated) await openTrash();
    } catch (error) {status.textContent = error.message;}
  })();
})();
