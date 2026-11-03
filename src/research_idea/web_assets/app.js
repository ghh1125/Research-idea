'use strict';
const $ = id => document.getElementById(id);
const state = {token: '', projects: [], project: null, tab: 'discussion', models: [], busy: false, fetching: false, fingerprint: '', toastTimer: null, connected: true};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storage = {
  get(key) { try { return localStorage.getItem('research-idea:' + key) || ''; } catch { return ''; } },
  set(key, value) { try { localStorage.setItem('research-idea:' + key, value); } catch { /* Private browsing can disable storage. */ } }
};
const modelName = id => ({'gpt-6-astra': 'GPT 6 astra', 'gpt-6.1-sol': 'GPT 6.1 sol', 'gpt-6.1-terra': 'GPT 6.1 terra', 'gpt-6-sol': 'GPT 6 sol', 'gpt-6-luna': 'GPT 6 luna'}[id] || id || '沿用 Codex');
const effortName = id => id || 'inherit';
const labels = {start:'开始',search:'检索文献',paper:'找到论文',read:'阅读文献',analysis:'分析进展',skill:'研究方法',concept:'研究构思',direction:'方向讨论',problem:'问题讨论',idea:'研究主张',error:'这一步未完成',budget:'预算提醒',stopped:'已暂停',update:'本轮修改',detail:'详细分析',retry:'正在重试',recovered:'已恢复',gap:'文献获取情况',saved:'已保存',system:'研究设置'};

function inline(text) {
  return esc(text).replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}
function markdown(text) {
  // Deliberately render a small Markdown subset; raw HTML is always escaped.
  const lines = String(text || '').split('\n');
  let html = '', list = '', code = false, paragraph = [];
  const flush = () => { if (paragraph.length) { html += '<p>' + paragraph.map(inline).join('<br>') + '</p>'; paragraph = []; } };
  const closeList = () => { if (list) { html += `</${list}>`; list = ''; } };
  for (let i=0; i<lines.length; i++) {
    const line=lines[i];
    if (line.trim().startsWith('```')) { flush(); closeList(); html += code ? '</code></pre>' : '<pre><code>'; code = !code; continue; }
    if (code) { html += esc(line) + '\n'; continue; }
    if (!line.trim()) { flush(); closeList(); continue; }
    if (line.includes('|') && i+1<lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i+1])) {
      flush();closeList();const cells=s=>s.trim().replace(/^\|/,'').replace(/\|$/,'').split('|');
      html+='<div class="table-wrap"><table><thead><tr>'+cells(line).map(c=>'<th>'+inline(c.trim())+'</th>').join('')+'</tr></thead><tbody>';
      i++;
      while(i+1<lines.length && lines[i+1].includes('|') && lines[i+1].trim()){i++;html+='<tr>'+cells(lines[i]).map(c=>'<td>'+inline(c.trim())+'</td>').join('')+'</tr>';}
      html+='</tbody></table></div>';continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    const bullet = line.match(/^\s*(?:[-*•]|\d+[.)、])\s+(.+)$/);
    if (heading) { flush(); closeList(); const level = heading[1].length; html += `<h${level}>${inline(heading[2])}</h${level}>`; }
    else if (bullet) { flush(); const type = /^\s*\d/.test(line) ? 'ol' : 'ul'; if (list !== type) { closeList(); html += type==='ol' ? `<ol start="${parseInt(line.trim(),10)}">` : '<ul>'; list = type; } html += `<li>${inline(bullet[1])}</li>`; }
    else if (/^---+$/.test(line)) { flush(); closeList(); html += '<hr>'; }
    else if (line.startsWith('> ')) { flush(); closeList(); html += `<blockquote>${inline(line.slice(2))}</blockquote>`; }
    else { closeList(); paragraph.push(line); }
  }
  flush(); closeList(); if (code) html += '</code></pre>';
  return html;
}

async function api(path, data) {
  const options = {headers: {}, signal: AbortSignal.timeout(25000)};
  if (data !== undefined) {
    options.method = 'POST'; options.headers = {'Content-Type':'application/json', 'X-Research-Token':state.token}; options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `请求失败 (${response.status})`);
  return body;
}
function notify(text, error=false) {
  clearTimeout(state.toastTimer); $('toast').textContent = text; $('toast').className = 'toast' + (error ? ' error' : ''); $('toast').hidden = false;
  state.toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 7000 : 3500);
}
function connection(ok) {
  state.connected = ok; $('offline').hidden = ok;
  $('offline').textContent = '本地服务连接中断，正在重新连接。尚未发送的文字已保留。';
  updateControls();
}
function saveDraft() { if (state.project) storage.set('draft:' + state.project.id, $('composer').value); }
function resizeComposer() { $('composer').style.height='auto';$('composer').style.height=Math.min(138,Math.max(43,$('composer').scrollHeight))+'px'; }
function showSidebar(open) {
  const mobile=matchMedia('(max-width:760px)').matches;
  $('sidebar').classList.toggle('open', open); $('scrim').hidden = !open || !mobile;
  $('sidebar').inert=mobile&&!open;$('menu').setAttribute('aria-expanded',String(open));
}
function title(value) { const line=String(value || '新的研究').split('\n')[0];return (line.split(/[，。]/)[0].replace(/^(我想研究|我希望研究|研究方向[：:]?)\s*/,'') || line).slice(0,58); }
function formatTime(iso) { if (!iso) return ''; const date = new Date(iso); return Number.isNaN(date.valueOf()) ? '' : date.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'}); }

function renderSidebar() {
  const p = state.project;
  $('project-count').textContent = state.projects.length;
  $('project-list').innerHTML = state.projects.map(item => `<div class="project-row ${p?.id === item.id ? 'active' : ''}"><button class="project-item" data-project="${esc(item.id)}" title="${esc(item.title)}" ${p?.id === item.id ? 'aria-current="true"' : ''}><svg class="project-icon" viewBox="0 0 24 24" aria-hidden="true">${item.pinned?'<path d="m8 3 8 0-1 7 4 4H5l4-4-1-7m4 11v7"/>':'<path d="M5 4h14v12H9l-4 4V4z"/>'}</svg><span class="project-name">${esc(title(item.title))}</span>${item.busy ? '<span class="running-dot"></span>' : ''}</button><div class="project-tools"><button data-pin="${esc(item.id)}" aria-label="${item.pinned?'取消置顶':'置顶'} ${esc(title(item.title))}" title="${item.pinned?'取消置顶':'置顶'}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 3 8 0-1 7 4 4H5l4-4-1-7m4 11v7"/></svg></button><button data-archive="${esc(item.id)}" aria-label="删除 ${esc(title(item.title))}" title="${item.busy?'请先停止运行':'移至回收站'}" ${item.busy?'disabled':''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/></svg></button></div></div>`).join('') || '<p class="muted small">从一个感兴趣的方向开始。</p>';
  const steps = p?.steps || ['明确方向','文献调研','方向讨论','深入分析','问题讨论','研究主张'].map((label,i) => ({label,state:i===0?'current':'pending'}));
  $('steps').innerHTML = steps.map((s,i) => `<li class="step ${s.state}" ${s.state === 'current' ? 'aria-current="step"' : ''}><span class="step-marker">${s.state === 'complete' ? '✓' : String(i+1).padStart(2,'0')}</span><span>${esc(s.label)}${s.state === 'current' ? `<small>${p?.busy ? (p.mode === 'chat' ? '正在讨论' : '进行中') : p?.can_continue ? '等待你的讨论' : p?.interrupted ? '可恢复' : '当前阶段'}</small>` : ''}</span></li>`).join('');
  $('stage-counter').textContent = p?.status === 'completed' ? '已完成' : `${(p?.stage || 0)+1} / 6`;
  $('stage-note').textContent = p?.busy ? '进度随实际研究步骤更新，关闭网页后仍可继续。' : p?.can_continue ? '可以追问、纠正或补充。讨论满意后，再进入下一步。' : '从你关心的方向出发，逐步形成有依据的研究主张。';
  $('usage').innerHTML = `<div>${p?.calls || 0} <small>/ ${p?.max_calls || 200} 次</small></div><div>${Math.floor((p?.elapsed || 0)/60)} <small>/ ${Math.floor((p?.max_seconds || 18000)/60)} 分钟</small></div>`;
  $('project-title').textContent = title(p?.title);
  $('paper-count').textContent = p?.paper_count || 0;
  $('stage-badge').textContent = p?.stopping ? '正在停止' : p?.busy ? '进行中' : p?.interrupted ? '已中断 · 可恢复' : p?.status === 'completed' ? '已形成研究主张' : p?.can_continue ? '等待讨论' : steps[p?.stage || 0].label;
}

function welcome() {
  return `<div class="welcome"><div class="orbital" aria-hidden="true"><svg viewBox="0 0 80 80"><g transform="translate(40 40)"><ellipse rx="14" ry="33"/><ellipse rx="14" ry="33" transform="rotate(60)"/><ellipse rx="14" ry="33" transform="rotate(120)"/><circle r="5" fill="currentColor" stroke="none"/></g></svg></div><span class="eyebrow">A SPACE FOR YOUR NEXT IDEA</span><h1>用好问题，开始下一项研究。</h1><p class="subtitle">带着一个方向，或者一个还不成熟的想法。<br>一起读懂已有工作，找到值得继续追问的问题。</p><div class="suggestions"><button class="suggestion" data-example="explore"><span class="suggestion-icon">↗</span><strong>探索一个方向</strong><small>从“自演化智能体”开始<br>梳理领域与重要问题</small></button><button class="suggestion" data-example="refine"><span class="suggestion-icon">◇</span><strong>打磨初步想法</strong><small>已有一个猜想？<br>一起理清动机与依据</small></button><button class="suggestion" data-example="question"><span class="suggestion-icon">⌁</span><strong>重新审视问题</strong><small>检查前提与已有回应<br>让研究问题更扎实</small></button></div><div class="welcome-bottom"><span></span> 文献有出处 · 讨论可追溯 · 进度自动保存 <span></span></div></div>`;
}
function emptyPanel(symbol, heading, text) { return `<div class="empty-panel"><div class="empty-symbol">${symbol}</div><h2>${esc(heading)}</h2><p>${esc(text)}</p></div>`; }
function timeline(p) {
  const entries = p.messages.map((m,i) => ({key:'m'+(m.id || i),time:m.time, role:m.role,text:m.content}));
  for (const e of p.events) {
    if (['assistant','thinking','context','system','evidence','saved'].includes(e.tag)) continue;
    entries.push({key:'e'+e.id,time:e.time,tag:e.tag,text:e.text});
  }
  if (p.can_continue && p.checkpoint_time && !p.events.some(e=>['direction','problem'].includes(e.tag))) {
    entries.push({key:'checkpoint',time:p.checkpoint_time,tag:p.stage===2?'direction':'problem',text:p.problem});
  }
  entries.sort((a,b) => String(a.time || '').localeCompare(String(b.time || '')));
  if (!entries.length) return welcome();
  return entries.map(e => {
    if (e.role || ['direction','problem','idea'].includes(e.tag)) {
      const user = e.role === 'user';
      return `<article class="message ${user ? 'user' : 'assistant'}"><div class="message-heading">${user ? '<span>你</span>' : `<span class="mini-mark">R</span><span>${e.tag ? esc(labels[e.tag]) : 'Research Idea'}</span>`}<time>${formatTime(e.time)}</time></div><div class="prose">${markdown(e.text)}</div></article>`;
    }
    const error = ['error','budget','stopped'].includes(e.tag);
    return `<details class="activity ${error ? 'error' : ''}" data-detail="${e.key}" ${error ? 'open' : ''}><summary><span>${esc(labels[e.tag] || '研究进展')}</span><span>· ${esc(e.text.split('\n')[0].slice(0,70))}</span></summary><div class="prose">${markdown(e.text)}</div></details>`;
  }).join('');
}
function renderContent(force=false) {
  const p = state.project;
  if (!p) return;
  const signature = JSON.stringify([state.tab,p.id,p.messages,p.events,p.report,p.problem,p.memory,p.papers,p.evidence,p.literature_landscape]);
  if (!force && signature === state.fingerprint) return;
  state.fingerprint = signature;
  const region = $('scroll-region'); const nearBottom = region.scrollHeight-region.scrollTop-region.clientHeight < 120;
  const expanded = new Set([...$('content').querySelectorAll('details[open][data-detail]')].map(el => el.dataset.detail));
  if (state.tab === 'discussion') $('content').innerHTML = timeline(p);
  else if (state.tab === 'papers') {
    $('content').innerHTML = p.papers.length ? `<div class="panel-heading"><div><span class="eyebrow">READING DESK</span><h2>研究所依据的文献</h2><p>${p.papers.length} 篇资料 · ${p.evidence.length} 条原文依据</p></div></div><div class="panel-note">资料类型按实际获取情况显示。只有摘要的论文不会被标记为已读全文。</div>` + p.papers.map(paper => `<article class="paper-card"><div class="paper-meta"><span>${esc(paper.year || '年份待核对')}</span><span>${esc(paper.content_kind === 'full_text' ? '全文资料' : paper.content_kind === 'abstract' ? '摘要资料' : paper.content_kind || '待阅读')}</span></div><h3>${/^https?:\/\//.test(paper.url || '') ? `<a href="${esc(paper.url)}" target="_blank" rel="noopener noreferrer">${esc(paper.title)}</a>` : esc(paper.title)}</h3>${paper.abstract ? `<details><summary>查看摘要</summary><p>${esc(paper.abstract)}</p></details>` : ''}${skimDetails(paper.id, p.literature_landscape)}${p.evidence.filter(e => e.paper_id === paper.id).map(e => `<details><summary>原文依据</summary><div class="prose">${markdown(e.quote || e.statement || '')}</div></details>`).join('')}</article>`).join('') : emptyPanel('⌁','给想法找到依据','开始文献调研后，真实检索与阅读的资料会出现在这里。已有 CLI 项目的论文也会同步显示。');
  } else if (state.tab === 'report') {
    const body = p.report || (p.stage >= 2 ? p.problem : '');
    $('content').innerHTML = body ? `<div class="panel-heading"><div><span class="eyebrow">RESEARCH ARGUMENT</span><h2>${p.status === 'completed' ? '当前研究主张' : '正在形成的研究论证'}</h2><p>背景 → 已有方法 → 问题 → 动机 → 研究主张</p></div><div class="report-actions"><button class="button secondary" data-download="report">导出 Markdown</button><button class="button secondary" data-tab="discussion">回到讨论</button></div></div><div class="prose report-prose">${markdown(body)}</div>` : emptyPanel('◇','好的主张，来自充分的讨论','完成文献调研和两次讨论后，在这里查看研究问题、动机和依据。你仍然可以提出修改意见。');
  } else if (state.tab === 'memory') {
    $('content').innerHTML = `<div class="panel-heading"><div><span class="eyebrow">THINGS WE KEEP IN MIND</span><h2>让讨论沿着你的目标继续</h2><p>持续要求、当前意见与原话来源，由研究引擎保存。</p></div></div><div class="prose report-prose">${markdown(p.memory)}</div>`;
  }
  for (const el of $('content').querySelectorAll('details[data-detail]')) if (expanded.has(el.dataset.detail)) el.open = true;
  if (force) region.scrollTop = state.tab === 'discussion' && p.messages.length ? region.scrollHeight : 0;
  else if (nearBottom) region.scrollTop = region.scrollHeight;
}

function renderModels() {
  const cfg = state.project?.config || {model:'gpt-6-astra',reasoning_effort:'medium'};
  const models = state.models.length ? state.models : [{id:'gpt-6-astra',levels:['low','medium','high']}];
  const choices = models.some(m => m.id === cfg.model) ? models : [{id:cfg.model,levels:[]},...models];
  const modelHtml = choices.map(m => `<option value="${esc(m.id)}">${esc(modelName(m.id))}</option>`).join('');
  if ($('model').innerHTML !== modelHtml) $('model').innerHTML = modelHtml;
  $('model').value = cfg.model;
  const levels = models.find(m => m.id === cfg.model)?.levels || ['low','medium','high'];
  const efforts = [...new Set(['',...levels,cfg.reasoning_effort])];
  const effortHtml = efforts.map(e => `<option value="${esc(e)}">${esc(effortName(e))}</option>`).join('');
  if ($('effort').innerHTML !== effortHtml) $('effort').innerHTML = effortHtml;
  $('effort').value = cfg.reasoning_effort;
}

function updateControls() {
  const p = state.project; const busy = !!(p?.busy || state.busy);
  $('send').disabled = busy || !state.connected || !$('composer').value.trim();
  $('new-project').disabled = state.busy || !state.connected;
  for (const id of ['model','effort','settings-open','budget-open']) $(id).disabled = busy || !state.connected;
  $('composer-area').hidden = state.tab !== 'discussion';
  $('composer').placeholder = p?.busy ? '运行中也可以先写下想法，完成后再发送…' : p?.messages.length ? '追问、纠正，或者补充你的想法…' : '说说你想研究什么，也可以补充初步想法与困惑…';
  $('run-status').hidden = !p?.busy;
  if (p?.busy) {
    const latest = [...p.events].reverse().find(e => ['search','read','analysis','concept','thinking','retry','start'].includes(e.tag));
    $('run-status').innerHTML = `<span class="spinner"></span><span class="status-copy">${esc(p.stopping ? '正在停止并保留已完成的进度…' : p.external ? '此研究正在命令行中运行' : latest?.text.split('\n')[0].slice(0,100) || '正在处理')}</span>${p.external ? '' : `<button class="stop-button" data-action="stop" ${p.stopping || state.busy ? 'disabled' : ''}>停止运行</button>`}`;
  }
  $('next-action').innerHTML = '';
  if (p && !p.busy && p.title !== '新的研究') {
    let heading, note, action, button;
    if (p.pending_message) { heading='上一条讨论未完成'; note='请重新发送该消息，或补充意见后再推进。'; action='retry'; button='重试消息'; }
    else if (p.can_continue) { heading=p.stage===2?'方向讨论中 · 满意后继续':'问题讨论中 · 满意后继续'; note='可以继续发消息追问，也可以推进下一阶段。'; action='continue'; button=p.stage===2?'继续深入分析 →':'整理研究主张 →'; }
    else if (p.status !== 'completed') { heading=p.stage===0?'先讨论方向，再读文献':'进度已保留'; note=p.stage===0?'先讨论清楚研究目标，再开始检索和阅读。':'已完成的步骤会复用。'; action='run'; button=p.stage===0?'开始文献调研 →':'恢复研究 →'; }
    if (heading) $('next-action').innerHTML = `<span title="${note}">${heading}</span><button class="button secondary" data-action="${action}" ${state.busy || !state.connected || (action!=='retry' && $('composer').value.trim()) ? 'disabled' : ''}>${button}</button>`;
  }
}
function render(force=false) { renderSidebar(); renderContent(force); renderModels(); updateControls(); }

async function selectProject(ident) {
  saveDraft();
  state.busy = true; updateControls();
  try {
    const p = await api('/api/projects/' + encodeURIComponent(ident));
    state.project = p; state.tab = 'discussion'; storage.set('selected', ident);
    $('composer').value = storage.get('draft:' + ident);
    resizeComposer();
    setTab('discussion'); showSidebar(false); render(true);
  } finally { state.busy = false; updateControls(); }
}
async function refresh() {
  if (state.fetching || state.busy) return;
  state.fetching = true;
  const ident = state.project?.id;
  try {
    if (!state.connected) state.token=(await api('/api/session')).token;
    const [list,p] = await Promise.all([api('/api/projects'),ident ? api('/api/projects/'+encodeURIComponent(ident)) : Promise.resolve(null)]);
    if (ident !== state.project?.id || state.busy) return;
    state.projects = list.projects; if (p) state.project = p;
    connection(true); render();
  } catch { connection(false); }
  finally { state.fetching = false; }
}
async function createProject() {
  saveDraft(); state.busy = true; updateControls();
  try {
    const p = await api('/api/projects', {model:state.project?.config.model || 'gpt-6-astra',effort:state.project?.config.reasoning_effort || 'medium'});
    state.project=p; state.projects.unshift(p); storage.set('selected',p.id); $('composer').value='';resizeComposer(); setTab('discussion'); render(true); showSidebar(false); $('composer').focus();
  } finally { state.busy = false; updateControls(); }
}
async function configure(values) {
  if (!state.project) return;
  state.busy = true; updateControls();
  try { state.project = await api('/api/projects/'+state.project.id+'/settings', values); renderModels(); notify('设置已保存'); }
  finally { state.busy = false; updateControls(); }
}
async function action(mode, message='') {
  if (state.busy || !state.project) return;
  state.busy = true; updateControls();
  try {
    await api('/api/projects/'+state.project.id+'/actions',{action:mode,message});
    if (mode === 'chat') { $('composer').value='';resizeComposer(); saveDraft(); }
  } finally { state.busy=false; updateControls(); }
  await refresh();
}
function setTab(tab) {
  if (!['discussion','papers','report','memory'].includes(tab)) return;
  state.tab = tab;
  for (const b of $('tabs').querySelectorAll('[data-tab]')) { if(b.dataset.tab === tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current'); }
  renderContent(true); updateControls();
}
function openSettings() {
  if (!state.project || state.project.busy) return;
  const c=state.project.config, f=$('settings-form');
  for(const k of ['max_calls','max_papers','timeout_s','constraints']) f.elements[k].value=c[k];
  f.elements.minutes.value=c.max_seconds/60; f.elements.auto_search.checked=c.auto_search;
  $('project-path').textContent=state.project.path; $('output-path').textContent=c.output_dir || '项目默认目录'; $('settings-error').textContent=''; $('settings-dialog').showModal();
}
function downloadReport() {
  const p=state.project;const body=p.report || p.problem;if(!body)return;
  const url=URL.createObjectURL(new Blob([body],{type:'text/markdown;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='research-idea-'+p.id+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function handleError(error) { notify(error.message || '操作未完成，请重试',true); renderModels(); }

async function projectOperation(ident,operation) {
  if(state.busy)return;
  const item=state.projects.find(p=>p.id===ident);
  state.busy=true;updateControls();
  try {
    await api('/api/projects/'+ident+'/actions',operation==='pin'?{action:'pin',pinned:!item.pinned}:{action:'archive'});
    state.projects=(await api('/api/projects')).projects;
    if(operation==='archive' && state.project?.id===ident){
      saveDraft();state.project=null;
      if(state.projects.length){state.busy=false;await selectProject(state.projects[0].id);}
      else {state.busy=false;await createProject();}
    } else if(state.project?.id===ident) state.project=await api('/api/projects/'+ident);
    renderSidebar();notify(operation==='pin'?(item.pinned?'已取消置顶':'已置顶'):'已移入回收站，可随时恢复');
  } finally {state.busy=false;updateControls();}
}
async function loadTrash() {
  const data=await api('/api/trash');
  $('trash-list').innerHTML=data.projects.length?data.projects.map(p=>`<div class="trash-row"><span>${esc(title(p.title))}</span><button class="button secondary" data-restore="${esc(p.id)}">恢复</button></div>`).join(''):'<p class="muted small">回收站是空的。</p>';
}
async function restoreProject(ident) {
  await api('/api/trash/'+ident+'/restore',{});await loadTrash();await refresh();notify('研究已恢复');
}

$('new-project').addEventListener('click',()=>createProject().catch(handleError));
$('composer').addEventListener('input',()=>{resizeComposer();saveDraft();updateControls();});
$('composer').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!$('send').disabled)$('composer-form').requestSubmit();}});
$('composer-form').addEventListener('submit',event=>{event.preventDefault();const text=$('composer').value.trim();if(text&&!$('send').disabled)action('chat',text).catch(handleError);});
$('model').addEventListener('change',()=>{const model=$('model').value;const m=state.models.find(m=>m.id===model);const effort=state.project.config.reasoning_effort;configure({model,reasoning_effort:m?.levels.includes(effort)?effort:(m?.default_effort || 'medium')}).catch(handleError);});
$('effort').addEventListener('change',()=>configure({reasoning_effort:$('effort').value}).catch(handleError));
$('settings-open').addEventListener('click',openSettings);$('budget-open').addEventListener('click',openSettings);
$('help-open').addEventListener('click',()=>$('help-dialog').showModal());
$('trash-open').addEventListener('click',()=>{loadTrash().then(()=>$('trash-dialog').showModal()).catch(handleError);});
$('menu').addEventListener('click',()=>showSidebar(true));$('scrim').addEventListener('click',()=>showSidebar(false));
$('settings-form').addEventListener('submit',async event=>{
  event.preventDefault();const f=event.currentTarget;const button=f.querySelector('button[type=submit]');button.disabled=true;
  try{await configure({max_calls:Number(f.elements.max_calls.value),max_seconds:Math.round(Number(f.elements.minutes.value)*60),max_papers:Number(f.elements.max_papers.value),timeout_s:Number(f.elements.timeout_s.value),constraints:f.elements.constraints.value,auto_search:f.elements.auto_search.checked});$('settings-dialog').close();}
  catch(error){$('settings-error').textContent=error.message;}
  finally{button.disabled=false;}
});
document.addEventListener('click',event=>{
  const b=event.target.closest('button');if(!b||b.disabled)return;
  if(b.dataset.project&&!state.busy)selectProject(b.dataset.project).catch(handleError);
  if(b.dataset.tab)setTab(b.dataset.tab);
  if(b.dataset.close)$(b.dataset.close).close();
  if(b.dataset.pin)projectOperation(b.dataset.pin,'pin').catch(handleError);
  if(b.dataset.archive)projectOperation(b.dataset.archive,'archive').catch(handleError);
  if(b.dataset.restore)restoreProject(b.dataset.restore).catch(handleError);
  if(b.dataset.download)downloadReport();
  if(b.dataset.action){
    if(b.dataset.action==='retry'){const last=[...state.project.messages].reverse().find(m=>m.role==='user');if(last)action('chat',last.content).catch(handleError);}
    else action(b.dataset.action).catch(handleError);
  }
  if(b.dataset.example){
    const examples={explore:'我想研究自演化智能体，目前还在方向探索阶段。请先帮我梳理这个领域的目标、主要研究思路和已有进展，再比较几个真正不同、值得深入的问题。请区分论文事实、解释和待验证的猜想。',refine:'我有一个关于自演化智能体的初步想法，想先和你一起理清它要解决的问题和研究动机。我的想法是：',question:'我想重新审视一个关于自演化智能体的研究问题。请帮我检查它的前提、现有工作的最强回应，以及剩下的困难是否值得研究。当前问题是：'};
    $('composer').value=examples[b.dataset.example];resizeComposer();saveDraft();updateControls();$('composer').focus();
  }
});

async function boot() {
  if(state.booting)return;state.booting=true;
  try {
    const session=await api('/api/session');state.token=session.token;
    state.projects=(await api('/api/projects')).projects;
    const selected=storage.get('selected'); const target=state.projects.find(p=>p.id===selected)||state.projects.find(p=>p.id==='main')||state.projects[0];
    if(target)await selectProject(target.id);else await createProject();
    api('/api/models?backend=codex').then(data=>{state.models=data.models||[];renderModels();}).catch(()=>notify('模型目录暂时不可读取，保留当前模型。'));
    connection(true);
  } catch(error) { connection(false);$('content').innerHTML=emptyPanel('↻','暂时无法连接本地研究服务',error.message); }
  finally {state.booting=false;}
}
showSidebar(false);
matchMedia('(max-width:760px)').addEventListener('change',()=>showSidebar(false));
boot();
setInterval(()=>{if(!state.token||!state.project)boot();else refresh();},2000);
window.addEventListener('beforeunload',saveDraft);

function skimDetails(id, landscape) {
  const n = landscape?.notes?.find(n => n.paper_id === id);
  if (!n) return '';
  const fields = [['研究问题','problem'],['主要思路','approach'],['摘要中的作者主张','claimed_progress'],['明确条件','conditions'],['与当前方向的联系','connection'],['值得补读的问题','reading_question']];
  return `<details><summary>查看泛读笔记</summary>${fields.filter(([,key]) => n[key]).map(([label,key]) => `<p><strong>${esc(label)}：</strong>${esc(n[key])}</p>`).join('')}<p>依据：${n.relevance === 'insufficient' ? '资料不足以形成摘要笔记' : '摘要泛读，未据此判定研究重叠'}</p></details>`;
}
