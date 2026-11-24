// ==UserScript==
// @name         CS2 Toolbox · Skybox Sync
// @namespace    cs2-toolbox
// @version      1.0.0
// @description  Inventory and upload explicitly selected personal FACEIT demos. Skybox auth stays on Skybox.
// @match        https://edge.skybox.gg/u/demos/personal*
// @run-at       document-idle
// @noframes
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

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
