// ==UserScript==
// @name         CS2 Toolbox Browser Companion
// @namespace    cs2-toolbox
// @version      1.1.4
// @description  Browser metadata and normal demo-button downloads for CS2 Toolbox.
// @match        https://www.faceit.com/*
// @match        https://faceit.com/*
// @match        https://www.hltv.org/*
// @match        https://hltv.org/*
// @match        https://edge.skybox.gg/u/demos/personal*
// @run-at       document-idle
// @noframes
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(() => {
  'use strict';
  const VERSION = 1;
  const STORAGE = 'cs2_toolbox_companion_v1';
  const PANEL = 'cs2-toolbox-browser';
  function canonical(value) {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    if (url.protocol !== 'https:' || !['faceit.com', 'hltv.org'].includes(host) || url.username || url.password || url.port)
      throw Error('Only HTTPS FACEIT and HLTV pages are supported.');
    url.hostname = 'www.' + host;
    url.pathname = url.pathname.replace(/\/+$/, '') || '/';
    url.search = new URLSearchParams([...url.searchParams].sort((a, b) =>
      a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0)).toString();
    url.hash = '';
    return url.href;
  }
  function parseLaunch(hash) {
    const params = new URLSearchParams(hash.replace(/^#/, ''));
    if (!params.has('cs2toolbox')) return null;
    const port = Number(params.get('port'));
    const token = params.get('pair') || '';
    if (params.get('cs2toolbox') !== String(VERSION) || !Number.isInteger(port) || port < 1024 || port > 65535 || !/^[\w-]{40,80}$/.test(token))
      throw Error('Invalid Toolbox connection. Start the job again from Toolbox.');
    return {port, token};
  }
  // Pure helpers are exercised under Node; no browser globals are read in this branch.
  if (typeof module === 'object' && module.exports) {
    module.exports = {canonical, parseLaunch};
    return;
  }
  if(location.origin==='https://edge.skybox.gg')return;
  let config, launchError;
  try {
    config = parseLaunch(location.hash);
    if (config) {
      sessionStorage.setItem(STORAGE, JSON.stringify(config));
      history.replaceState(null, '', location.pathname + location.search);
    } else {
      const saved = sessionStorage.getItem(STORAGE);
      config = saved ? JSON.parse(saved) : null;
    }
  } catch (error) { launchError = error.message; }
  const owner = sessionStorage.cs2ToolboxTab ||= crypto.randomUUID();
  let busy = false, paused = false, current;
  const panel = document.createElement('section');
  panel.id = PANEL;
  panel.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:2147483647;width:310px;background:#15212d;color:#edf3f8;border:1px solid #75c7fb;border-radius:8px;padding:16px;font:13px/1.5 Segoe UI,sans-serif;box-shadow:0 4px 20px #0008';
  const title = document.createElement('strong');
  title.textContent = 'CS2 Toolbox · Browser companion';
  const note = document.createElement('p');
  note.textContent = launchError || 'Start a download or review from CS2 Toolbox. The older Coach Tools collectors should be disabled.';
  const control = document.createElement('button');
  control.textContent = 'Pause browser';
  control.onclick = () => { paused = !paused; control.textContent = paused ? 'Resume browser' : 'Pause browser'; };
  panel.append(title, note, control);
  document.body.append(panel);
  const api = (route, data = {}) => new Promise((resolve, reject) => {
    GM_xmlhttpRequest({method: 'POST', url: `http://127.0.0.1:${config.port}${route}`, timeout: 15000,
      headers: {'Content-Type': 'application/json', 'X-CS2-Token': config.token},
      data: JSON.stringify({...data, version: VERSION, owner, capabilities: ['download-retry-v1']}),
      onload: result => {
        try {
          const body = JSON.parse(result.responseText);
          if (result.status !== 200) throw Error(body.error || 'Toolbox rejected this request.');
          resolve(body);
        } catch (error) { reject(error); }
      },
      onerror: () => reject(Error('Toolbox helper is offline. Start the job again from Toolbox.')),
      ontimeout: () => reject(Error('Toolbox helper timed out. Check the app, then retry.')),
    });
  });
  const visible = node => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden';
  function snapshot() {
    if (location.hostname.replace(/^www\./, '') !== 'hltv.org') throw Error('FACEIT metadata comes from the Data API.');
    const nodes = location.pathname === '/results' ? [...document.querySelectorAll('.results-holder')]
      : /^\/team\//.test(location.pathname) ? [...document.querySelectorAll('.profile-team-name')]
      : [...document.querySelectorAll('.teamsBox,.mapholder,a[data-demo-link],a[href^="/download/demo/"]')];
    if (!nodes.length) return null; // Page still loading, blocked, or selectors changed.
    if (/^\/matches\//.test(location.pathname) && !document.querySelector('.teamsBox .teamName')) return null;
    // Send public match/result elements only. Never serialize the complete page, script state, cookies, or inputs.
    const html = nodes.map(node => {
      const copy = node.cloneNode(true);
      copy.querySelectorAll('script,style,input,textarea,noscript,iframe').forEach(child => child.remove());
      return copy.outerHTML;
    }).join('\n');
    if (html.length > 2500000) throw Error('HLTV result metadata exceeds the companion message limit.');
    return html;
  }
  function watchButton() {
    if (location.hostname.replace(/^www\./, '') === 'hltv.org')
      return [...document.querySelectorAll('[data-demo-link-button]')].find(visible);
    return [...document.querySelectorAll('button,[role="button"]')].find(node =>
      !node.closest('#' + PANEL) && visible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true'
      && /^watch demo$/i.test(node.textContent.trim()));
  }
  async function tick() {
    if (!config || paused || busy) return;
    busy = true;
    let task;
    try {
      const legacy = document.querySelector('#faceit-verified-panel') || [...document.querySelectorAll('section strong')]
        .find(node => /^CS2 Coach Tools.*HLTV v/i.test(node.textContent.trim()));
      if (legacy) throw Error('Disable the older FACEIT/HLTV Coach Tools collectors in Violentmonkey, then reload this page.');
      const state = await api('/state');
      task = state.task;
      if (!task) { note.textContent = 'Waiting for the next Toolbox task.'; return; }
      if (canonical(location.href) !== canonical(task.url)) {
        // Only desktop-issued, allowlisted provider URLs can enter a task.
        const target = new URL(canonical(task.url));
        if (target.hostname.replace(/^www\./, '') !== location.hostname.replace(/^www\./, ''))
          throw Error('Wrong provider tab. Start this job again from Toolbox.');
        const previous = JSON.parse(sessionStorage.cs2ToolboxNavigation || '{}');
        const attempts = previous.url === target.href ? previous.attempts + 1 : 1;
        if (attempts > 3) throw Error('Navigation repeatedly failed. Check login or site verification, then restart from Toolbox.');
        sessionStorage.cs2ToolboxNavigation = JSON.stringify({url: target.href, attempts});
        location.assign(target.href);
        return;
      }
      sessionStorage.removeItem('cs2ToolboxNavigation');
      if (task.reload && task.status === 'pending' && sessionStorage.getItem('cs2ToolboxReload') !== task.id) {
        sessionStorage.setItem('cs2ToolboxReload', task.id);
        note.textContent = 'No download detected. Refreshing before retry…';
        location.reload();
        return;
      }
      if (task.status !== 'pending') {
        note.textContent = task.mode === 'download'
          ? 'Download requested. Let the browser finish; select its archive in Toolbox when asked. A click is not download confirmation.'
          : 'Page metadata sent. Waiting for the next page.';
        return;
      }
      if (current?.id !== task.id) current = {id: task.id, started: Date.now()};
      const elapsed = Date.now() - current.started;
      if (task.reload && elapsed < 3000) {
        note.textContent = 'Waiting three seconds after refresh before retrying…';
        return;
      }
      if (task.mode === 'inspect') {
        const html = snapshot();
        if (!html) {
          note.textContent = 'Waiting for HLTV metadata. Complete any browser verification yourself.';
          if (elapsed > 45000) throw Error('HLTV metadata did not load. Check verification, page format, or availability.');
          return;
        }
        await api('/snapshot', {id: task.id, url: location.href, html});
        note.textContent = 'Public match metadata sent to Toolbox.';
      } else if (task.mode === 'download') {
        let watch = watchButton();
        if (!watch) {
          note.textContent = 'Waiting for an enabled demo button. Check login and demo availability.';
          if (elapsed > 45000) throw Error('No enabled demo button. Check login, page language, site verification, or availability. No expiry was assumed.');
          return;
        }
        if (location.hostname.replace(/^www\./, '') === 'faceit.com') {
          // FACEIT can display an enabled button before its handler is ready.
          await new Promise(resolve => setTimeout(resolve, 500));
          if (paused || canonical(location.href) !== canonical(task.url)) return;
          watch = watchButton(); // Hydration can replace or disable the element.
          if (!watch) return;
        }
        // Claim first; a refresh, lost acknowledgement, or another tab cannot produce a second click.
        const claim = await api('/claim', {id: task.id, url: location.href});
        if (claim.click === false) {
          note.textContent = 'Download activity detected. Waiting for the existing file.';
          return;
        }
        watch.scrollIntoView({block: 'center'});
        watch.click();
        if (claim.acknowledge_click) await api('/clicked', {id: task.id, url: location.href});
        note.textContent = 'Download requested through the normal site button. Keep this tab open.';
      } else throw Error('Unsupported task. Update the Toolbox companion.');
    } catch (error) {
      paused = true;
      control.textContent = 'Resume browser';
      note.textContent = error.message;
      if (task && canonical(location.href) === canonical(task.url))
        api('/problem', {id: task.id, url: location.href, message: error.message}).catch(() => {});
    } finally { busy = false; }
  }
  setInterval(tick, 1500);
  tick();
})();

// Skybox handler; kept in the existing companion to avoid a second installation.
if(typeof module==='undefined' && location.origin==='https://edge.skybox.gg'){
(() => {
  'use strict';
  const VERSION=1, STORAGE='cs2_toolbox_skybox_v1';
  const faceitPattern=/1-[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}/ig;
  const hashPattern=/^(?:[a-f0-9]{16}|[a-f0-9]{64})$/;
  function pairing(hash){
    const p=new URLSearchParams(hash.replace(/^#/,''));
    if(!p.has('cs2skybox'))return null;
    const port=Number(p.get('port')),token=p.get('pair')||'';
    if(p.get('cs2skybox')!=='1'||!Number.isInteger(port)||port<1024||port>65535||! /^[\w-]{40,80}$/.test(token))throw Error('Invalid Toolbox pairing.');
    return {port,token};
  }
  function pendingIdentity(entries){
    if(!Array.isArray(entries))throw Error('Skybox pending inventory was not returned.');
    const hashes=new Set(),ids=new Set();
    for(const entry of entries){
      const upload=entry.upload||entry;
      if(entry.error||upload.error)continue;
      const name=String(upload.sourceName||'');
      for(const id of name.match(faceitPattern)||[])ids.add(id.toLowerCase());
      const full=name.match(/__([a-f0-9]{64})\.dem$/i);if(full)hashes.add(full[1].toLowerCase());
      if(typeof upload.sourceUuid==='string'&&hashPattern.test(upload.sourceUuid))hashes.add(upload.sourceUuid);
    }
    return {hashes:[...hashes],ids:[...ids]};
  }
  function uploadUrl(value){
    const u=new URL(value);
    if(u.protocol!=='https:'||u.username||u.password||u.port||!u.hostname.includes('.')||
      /^(?:localhost|127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(u.hostname))throw Error('Unsafe Skybox storage destination.');
    return u.href;
  }
  if(typeof module==='object'&&module.exports){module.exports={pairing,pendingIdentity,uploadUrl};return}
  if(location.origin!=='https://edge.skybox.gg'||location.pathname!=='/u/demos/personal')return;
  if(document.getElementById('cs2-toolbox-skybox'))return;
  let config;
  try{
    config=pairing(location.hash);
    if(config){sessionStorage.setItem(STORAGE,JSON.stringify(config));history.replaceState(null,'',location.pathname+location.search)}
    else config=JSON.parse(sessionStorage.getItem(STORAGE)||'null');
  }catch{return}
  if(!config)return;
  const owner=sessionStorage.cs2SkyboxOwner ||= crypto.randomUUID();
  const panel=document.createElement('section');panel.id='cs2-toolbox-skybox';panel.style.cssText='position:fixed;right:18px;bottom:18px;z-index:2147483647;width:320px;padding:16px;background:#14231d;color:#edf8f1;border:1px solid #55d790;border-radius:8px;font:13px/1.5 Segoe UI,sans-serif';
  const heading=document.createElement('strong');heading.textContent='CS2 Toolbox · Skybox';
  const note=document.createElement('p');note.textContent='Paired to the current Toolbox job. Only its selected demos can be read.';
  const stop=document.createElement('button');stop.textContent='Pause';panel.append(heading,note,stop);document.body.append(panel);
  let paused=false,busy=false,fileCache=null,lastId=null;
  stop.onclick=()=>{paused=!paused;stop.textContent=paused?'Resume':'Pause'};
  function local(route,body={}){
    return new Promise((resolve,reject)=>GM_xmlhttpRequest({method:'POST',url:`http://127.0.0.1:${config.port}${route}`,timeout:30000,
      headers:{'Content-Type':'application/json','X-CS2-Skybox':config.token},data:JSON.stringify({version:VERSION,owner,...body}),
      onload:r=>{try{const data=JSON.parse(r.responseText);if(r.status!==200)throw Error(data.error||'Toolbox connection expired.');resolve(data)}catch(e){reject(e)}},
      onerror:()=>reject(Error('Toolbox connection closed. Restart the job in Toolbox.')),ontimeout:()=>reject(Error('Toolbox read timed out.'))}));
  }
  async function gql(query,variables={}){
    // This is the same storage key/header used by the observed Skybox client.
    // The value goes ONLY to Skybox /api; never to the local bridge or logs.
    const auth=localStorage.getItem('@skybox:authtoken');
    if(!auth)throw Error('Sign in to Skybox, then restart the Toolbox job.');
    const response=await fetch('/api',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json',authorization:'Bearer '+auth},body:JSON.stringify({query,variables}),signal:AbortSignal.timeout(60000)});
    if(!response.ok)throw Error('Skybox request rejected. Check login, access and service availability.');
    const body=await response.json();
    if(body.errors?.length||!body.data){
      const operation=query.match(/(?:query|mutation)\s+(Toolbox[A-Za-z]+)/)?.[1]||'ToolboxUnknown';
      // Only provider error codes and our fixed operation names leave the browser.
      const codes=(body.errors||[]).map(e=>e.extensions?.code||e.code||'unknown').filter(c=>typeof c==='string'&&/^[a-zA-Z_]{1,60}$/.test(c));
      const issue=operation+': '+([...new Set(codes)].join(', ')||'unknown');
      throw Object.assign(Error('Skybox rejected '+issue+'. Check sign-in and access; no upload was retried.'),{issue});
    }
    return body.data;
  }
  async function account(expected){
    const id=(await gql('query ToolboxAccount { me { uuid } }')).me?.uuid;
    if(!id||expected&&id!==expected)throw Error('Skybox account changed. Restart the job for this account.');
    return id;
  }
  const inventoryQuery=`query ToolboxPersonalInventory($pageNumber:Int!,$pageSize:Int!){
    matchAnalysis(teamId:null,input:{orderBy:insertedAt,direction:desc,gameTitle:cs2,public:false}){
      matches(pagination:{pageNumber:$pageNumber,pageSize:$pageSize}){
        entries{hash} totalEntries totalPages page{pageNumber}
      }
    }
  }`;
  const pendingQuery=`query ToolboxPending { myPendingMatches {
    ... on PendingMatchUpload { sourceName sourceUuid error { errorType } }
    ... on PendingMatchProcessing { upload { sourceName sourceUuid error { errorType } } error { errorType } }
  } }`;
  async function inventory(){
    const id=await account(),hashes=new Set(),matchIds=new Set();let pages=1,total=null;
    for(let page=1;page<=pages;page++){
      if(page>5000)throw Error('Skybox inventory exceeded 100,000 entries. No uploads started.');
      note.textContent=`Reading Skybox inventory · page ${page}/${pages}`;
      const result=(await gql(inventoryQuery,{pageNumber:page,pageSize:20})).matchAnalysis?.matches;
      if(!result||!Array.isArray(result.entries)||!Number.isInteger(result.totalPages)||!Number.isInteger(result.totalEntries)||result.page?.pageNumber!==page)throw Error('Skybox inventory/pagination format changed.');
      if(total!==null&&total!==result.totalEntries)throw Error('Skybox inventory changed during paging. Restart to refresh.');
      total=result.totalEntries;pages=Math.max(1,result.totalPages);
      for(const entry of result.entries){
        if(!hashPattern.test(entry.hash))throw Error('Skybox returned an unfamiliar match hash.');
        hashes.add(entry.hash);

      }
    }
    if(total!==hashes.size)throw Error('Skybox inventory is incomplete or changed during paging.');
    const pending=pendingIdentity((await gql(pendingQuery)).myPendingMatches);await account(id);
    return {complete:true,account:id,count:total,hashes:[...hashes],match_ids:[...matchIds],pending_hashes:pending.hashes,pending_ids:pending.ids};
  }
  async function selectedFile(task){
    if(fileCache?.ticket===task.file.ticket)return fileCache.file;
    const parts=[];let offset=0;
    while(offset<task.file.bytes){
      note.textContent=`Reading selected demo · ${Math.floor(offset/task.file.bytes*100)}%`;
      const chunk=await local('/file',{id:task.id,ticket:task.file.ticket,offset});
      const bytes=Uint8Array.from(atob(chunk.bytes),c=>c.charCodeAt(0));
      if(chunk.offset!==offset||chunk.next!==offset+bytes.length||!bytes.length||chunk.next>task.file.bytes)throw Error('Invalid demo chunk.');
      parts.push(bytes);offset=chunk.next;
    }
    const file=new File(parts,task.file.filename,{type:'application/octet-stream',lastModified:task.file.modified});
    if(await file.slice(0,7).text()!=='PBDEMS2')throw Error('Only CS2 .dem files are supported.');
    fileCache={ticket:task.file.ticket,file,hash:null};return file;
  }
  async function hashFile(file){
    // The BLAKE3 worker/wasm URL is observed in Skybox's current public client.
    const worker=new Worker('/assets/hash-file.worker-CyzPhHO1.js');
    try{
      return await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(Error('Skybox file hash timed out.')),300000);
        worker.onerror=()=>{clearTimeout(timer);reject(Error('Skybox hash worker changed or could not load.'))};
        worker.onmessage=e=>{clearTimeout(timer);/^[a-f0-9]{64}$/.test(e.data)?resolve(e.data):reject(Error('Invalid Skybox file hash.'))};
        worker.postMessage({t:'init',u:location.href});worker.postMessage({t:'hash',data:file});
      });
    }finally{worker.terminate()}
  }
  const addQuery=`mutation ToolboxAddExisting($hash:String!,$filename:String!,$modified:DateTime!){
    addFromHash(hash:$hash,filename:$filename,teamId:null,gameTitle:cs2,fileModifiedAt:$modified){errors{code type}}
  }`;
  const prepareQuery=`mutation ToolboxPrepare($filename:String!,$modified:DateTime!){
    presignedUpload(filename:$filename,teamId:null,gameTitle:cs2,fileModifiedAt:$modified){errors{type}payload{presignedUrl replayUpload{id}}}
  }`;
  async function upload(task,file,digest){
    if(digest!==task.hash)throw Error('Selected demo hash changed.');
    await account(task.account);
    // Refresh immediately before mutations, including pending jobs accepted elsewhere.
    const current=await inventory();if(current.account!==task.account)throw Error('Skybox account changed.');
    if(current.hashes.includes(digest)||current.hashes.includes(digest.slice(0,16))||current.pending_hashes.includes(digest))return {state:'already_present'};
    const filename=task.match_id+'__'+digest+'.dem',modified=new Date(file.lastModified).toISOString();
    for(const hash of [digest,digest.slice(0,16)]){
      const result=(await gql(addQuery,{hash,filename,modified})).addFromHash;
      if(!result||!Array.isArray(result.errors))throw Error('Skybox add-existing response was not recognized.');
      if(!result.errors.length)return {state:'accepted'};
      if(result.errors.some(e=>e.code!=='not_found'))throw Error('Skybox rejected add-existing (quota, subscription or access). No retry was made.');
    }
    const prep=(await gql(prepareQuery,{filename,modified})).presignedUpload;
    if(!prep||prep.errors?.length||!prep.payload?.replayUpload?.id||!prep.payload?.presignedUrl)throw Error('Skybox rejected upload preparation. Check quota and access.');
    const destination=uploadUrl(prep.payload.presignedUrl);
    note.textContent='Uploading selected demo to Skybox…';
    const result=await fetch(destination,{method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:file,
      credentials:'omit',redirect:'error',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(900000)});
    if(!result.ok)throw Error('Upload outcome is uncertain. Check Skybox before retrying.');
    return {state:'accepted'};
  }
  async function poll(){
    if(paused||busy)return;busy=true;
    try{
      const {task}=await local('/state');
      if(!task||task.status!=='pending'||task.id===lastId)return;
      // A claimed task is never automatically replayed after a lost response.
      await local('/claim',{id:task.id});lastId=task.id;
      let result;
      try{
        if(task.mode==='inventory')result=await inventory();
        else{
          await account(task.account);
          const file=await selectedFile(task);const hash=fileCache.hash||await hashFile(file);fileCache.hash=hash;
          result=task.mode==='hash'?{hash}:task.mode==='upload'?await upload(task,file,hash):null;
          if(!result)throw Error('Unknown Toolbox task.');
        }
        await local('/result',{id:task.id,result});note.textContent=task.mode==='inventory'?`Inventory complete · ${result.count} demos`:
          task.mode==='hash'?'Demo identity checked.':'Skybox accepted the demo; processing may continue.';
      }catch(error){note.textContent=error.message;paused=true;stop.textContent='Resume';await local('/problem',{id:task.id,issue:error.issue||''}).catch(()=>{})}
    }catch(error){note.textContent=error.message}
    finally{busy=false}
  }
  setInterval(poll,1200);poll();
})();

}
