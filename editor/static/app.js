(() => {
  const $ = id => document.getElementById(id);
  let items=[],category='',article=null,token='',viewer=null,editor=null,requestId=0,baseline='',saving=false,uploading=0,syncing=false,authenticated=false;
  async function api(url,payload) {
    const options={cache:'no-store'};
    if(payload){options.method='POST';options.headers={'Content-Type':'application/json','X-Editor-Token':token};options.body=JSON.stringify(payload);}
    const response=await fetch(url,options),data=await response.json();
    if(!response.ok){if(response.status===401){authenticated=false;updateAuth();const config=await fetch('/api/config',{cache:'no-store'}).then(r=>r.json());token=config.token;}$('login-status').textContent=data.error||'';throw new Error(data.error||'操作失败');}return data;
  }
  const dirty=()=>editor&&($('title-input').value!==article.title||editor.getMarkdown()!==baseline);
  const safeLeave=()=>!dirty()||window.confirm('还有未保存的修改，确定放弃吗？');
  function updateSave(){ $('save').disabled=!authenticated||saving||uploading>0; }
  function updateAuth(){ $('account').textContent=authenticated?'退出登录':'管理员登录';$('edit').hidden=!authenticated||!!editor;$('sync').hidden=!authenticated||!!editor;updateSave(); }
  function closeEditor(){if(editor){editor.destroy();editor=null;}$('editor').hidden=true;$('viewer').hidden=false;$('title-field').hidden=true;$('title').hidden=false;$('edit').hidden=false;$('sync').hidden=false;$('save').hidden=true;$('cancel').hidden=true;updateAuth();}
  function showHome(){if(saving||syncing||uploading||!safeLeave())return;requestId++;closeEditor();$('library').hidden=false;$('article').hidden=true;history.replaceState(null,'',location.pathname);$('article-base').href='/';}
  function renderList(){
    const query=$('search').value.trim().toLocaleLowerCase();const shown=items.filter(a=>a.kind==='文章'&&(!category||a.module===category)&&a.title.toLocaleLowerCase().includes(query));
    $('articles').replaceChildren();$('count').textContent=shown.length+' 篇文章';
    shown.forEach(a=>{const button=document.createElement('button');button.type='button';button.className='article-card';const meta=document.createElement('span');meta.textContent=[a.module,a.date.slice(0,10)].filter(Boolean).join(' · ');const title=document.createElement('strong');title.textContent=a.title;button.append(meta,title);button.addEventListener('click',()=>openArticle(a.path));$('articles').append(button);});
    if(!shown.length){const p=document.createElement('p');p.textContent='这个分类暂时没有文章。';$('articles').append(p);}
  }
  function showArticle(){
    $('title').textContent=article.title;$('title-input').value=article.title;$('meta').textContent=[article.module,article.date.slice(0,10)].filter(Boolean).join(' · ');
    const parent=article.path.split('/').slice(0,-1).map(encodeURIComponent).join('/');$('article-base').href='/media/content/'+(parent?parent+'/':'');
    if(viewer)viewer.destroy();viewer=toastui.Editor.factory({el:$('viewer'),viewer:true,initialValue:article.body,usageStatistics:false});
    $('sync').disabled=false;$('edit').disabled=!article.editable;updateAuth();$('status').textContent=article.editable?'': '此页包含专用图表组件，暂时只读。';
  }
  async function openArticle(path){
    if(saving||syncing||uploading||!safeLeave())return;closeEditor();const id=++requestId;$('library').hidden=true;$('article').hidden=false;$('edit').disabled=true;$('sync').disabled=true;$('status').textContent='正在打开文章…';$('title').textContent='';if(viewer){viewer.destroy();viewer=null;}
    try{const data=await api('/api/article?path='+encodeURIComponent(path));if(id!==requestId)return;article=data.article;showArticle();history.replaceState(null,'','#article='+encodeURIComponent(path));}
    catch(error){if(id===requestId)$('status').textContent=error.message;}
  }
  async function uploadImage(blob,callback){
    uploading++;updateSave();$('status').textContent='正在保存图片…';
    try{
      if(blob.size>8*1024*1024)throw new Error('图片不能超过 8 MB');
      const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
      const result=await api('/api/upload',{path:article.path,data:btoa(binary)});callback(result.url,blob.name||'图片');$('status').textContent='图片已插入，请保存文章。';
    }catch(error){$('status').textContent=error.message;}finally{uploading--;updateSave();}
  }
  function startEditing(){
    if(!authenticated||!article?.editable||editor||syncing)return;$('sync').hidden=true;$('viewer').hidden=true;$('editor').hidden=false;$('title').hidden=true;$('title-field').hidden=false;$('edit').hidden=true;$('save').hidden=false;$('cancel').hidden=false;
    editor=new toastui.Editor({el:$('editor'),height:'auto',minHeight:'500px',initialEditType:'wysiwyg',hideModeSwitch:true,language:'zh-CN',initialValue:article.body,usageStatistics:false,toolbarItems:[['heading','bold','italic','strike'],['hr','quote'],['ul','ol','task','indent','outdent'],['table','image','link'],['code','codeblock']],hooks:{addImageBlobHook:uploadImage}});
    baseline=editor.getMarkdown();$('status').textContent='直接修改正文，可使用工具栏或粘贴、拖入图片。';updateSave();
  }
  async function save(){
    if(!authenticated||!editor||saving||uploading)return;
    if(!dirty()){closeEditor();showArticle();$('status').textContent='没有修改，文件保持原样。';return;}
    saving=true;updateSave();$('editor').inert=true;$('title-input').disabled=true;$('cancel').disabled=true;$('status').textContent='正在保存 Markdown…';
    try{const data=await api('/api/save',{path:article.path,title:$('title-input').value,body:editor.getMarkdown(),revision:article.revision});article=data.article;closeEditor();showArticle();$('status').textContent='已保存到本地 Markdown，尚未同步 GitHub。';const index=items.findIndex(a=>a.path===article.path);if(index>=0)items[index]=article;renderList();}
    catch(error){$('status').textContent=error.message;}
    finally{saving=false;$('editor').inert=false;$('title-input').disabled=false;$('cancel').disabled=false;updateSave();}
  }
  async function sync(){
    if(!authenticated||!article||editor||saving||uploading||syncing)return;
    syncing=true;$('sync').disabled=true;$('edit').disabled=true;$('status').textContent='正在同步到 GitHub…';
    try{const result=await api('/api/sync',{path:article.path,revision:article.revision});$('status').textContent=result.changed?'已同步到 GitHub，等待网站构建完成。':'这篇文章已与 GitHub 一致。';}
    catch(error){$('status').textContent='未完成同步：'+error.message;}
    finally{syncing=false;$('sync').disabled=false;$('edit').disabled=!article.editable;updateAuth();}
  }
  $('account').addEventListener('click',async()=>{
    if(saving||syncing||uploading)return;
    if(authenticated){if(!safeLeave())return;try{const data=await api('/api/logout',{});authenticated=false;token=data.token;closeEditor();if(article)showArticle();updateAuth();}catch(error){if(article)$('status').textContent=error.message;}return;}
    try{const config=await api('/api/config');token=config.token;$('login-status').textContent=config.configured?'':'请先在项目终端运行 setup-editor.cmd 设置密码。';$('login-submit').disabled=!config.configured;$('login-dialog').showModal();$('password').focus();}catch(error){$('count').textContent=error.message;}
  });
  $('login-cancel').addEventListener('click',()=>{$('password').value='';$('login-dialog').close();});
  $('login-dialog').addEventListener('close',()=>{$('password').value='';});
  $('login-form').addEventListener('submit',async event=>{
    event.preventDefault();$('login-submit').disabled=true;$('login-status').textContent='正在登录…';
    const password=$('password').value;$('password').value='';
    try{const data=await api('/api/login',{password});token=data.token;authenticated=true;updateAuth();$('login-dialog').close();if(article)$('status').textContent='已登录，可以编辑和同步文章。';}
    catch(error){$('login-status').textContent=error.message;}finally{$('login-submit').disabled=false;}
  });
  $('sync').addEventListener('click',sync);
  $('home').addEventListener('click',showHome);$('back').addEventListener('click',showHome);$('edit').addEventListener('click',startEditing);$('save').addEventListener('click',save);$('cancel').addEventListener('click',()=>{if(!saving&&!uploading&&safeLeave()){closeEditor();showArticle();}});$('search').addEventListener('input',renderList);
  window.addEventListener('beforeunload',event=>{if(dirty()||saving||syncing||uploading){event.preventDefault();event.returnValue='';}});
  async function init(){
    try{if(!window.toastui?.Editor)throw new Error('编辑器未加载，请刷新后重试');const config=await api('/api/config');token=config.token;authenticated=config.authenticated;updateAuth();items=(await api('/api/articles')).articles;
      ['全部','日记','英语','阅读','金句','其他'].forEach(name=>{const button=document.createElement('button');button.type='button';button.textContent=name;button.setAttribute('aria-pressed',String(name==='全部'));button.addEventListener('click',()=>{category=name==='全部'?'':name;$('categories').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));renderList();});$('categories').append(button);});renderList();
      const params=new URLSearchParams(location.hash.slice(1));if(params.has('article'))await openArticle(params.get('article'));
    }catch(error){$('count').textContent=error.message;}
  }
  init();
})();
