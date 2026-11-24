/* Portable report interactions: no network, account or running game required. */
const data=JSON.parse(document.getElementById('report-data').textContent);
const $=id=>document.getElementById(id);
const storageKey='cs2-coaching:'+data.digest;
let selectedCase=0, viewerReady=false, pendingCase=null, opener=null;
function loadPreference(key,fallback){try{return localStorage.getItem(key)??fallback}catch{return fallback}}
function savePreference(key,value){try{localStorage.setItem(key,value);return true}catch{return false}}
const noteFields=['information','plan','adjustment'];
let savedNotes={};
try{const parsed=JSON.parse(loadPreference(storageKey+':notes','{}'));if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed))savedNotes=parsed}catch{/* A damaged local copy must not stop replay or export. */}
const reviewNotes=Object.fromEntries(data.cases.map(item=>[item.record.id,Object.fromEntries(noteFields.map(field=>[field,typeof savedNotes[item.record.id]?.[field]==='string'?savedNotes[item.record.id][field].slice(0,4000):'']))]));
for(const input of document.querySelectorAll('[data-note]'))input.oninput=()=>{
 reviewNotes[data.cases[selectedCase].record.id][input.dataset.note]=input.value.slice(0,4000);
 const saved=savePreference(storageKey+':notes',JSON.stringify(reviewNotes));
 $('notes-status').textContent=saved?'Saved in this browser. Export a copy to keep with your report.':'Browser storage is unavailable. Your notes remain in this open report; export a copy before closing.';
};
$('export-notes').onclick=()=>{
 const exported={version:1,exportedAt:new Date().toISOString(),evidenceDigest:data.digest,
  player:{steamid:data.player.steamid,name:data.player.name},
  practiceMatches:Array.from(document.querySelectorAll('[data-match]'),input=>({match:Number(input.dataset.match),reviewed:input.checked})),
  situations:data.cases.map(item=>{const r=item.record;return {roundId:r.id,demoSha256:r.sha,source:r.source,round:r.round,map:r.map,date:r.date,tickrate:r.tickrate,openingTick:r.events.find(e=>e.enemy).tick,notes:{...reviewNotes[r.id]}}})};
 const exportText=JSON.stringify(exported,null,2);
 $('notes-export-text').value=exportText;$('notes-export').hidden=false;
 const url=URL.createObjectURL(new Blob([exportText],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='CS2-review-'+data.player.steamid.replace(/[^a-zA-Z0-9_-]/g,'_')+'.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 $('notes-status').textContent='Export prepared for all situations. If the download does not complete, copy the export text below.';
};
$('select-export').onclick=()=>{$('notes-export-text').focus();$('notes-export-text').select()};
function setTheme(theme){document.documentElement.dataset.theme=theme;$('theme').textContent=theme==='dark'?'Light view ☼':'Dark view ☾';$('theme').setAttribute('aria-label','Switch to '+(theme==='dark'?'light':'dark')+' appearance')}
setTheme(loadPreference('cs2-report-theme','dark'));
$('theme').onclick=()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';setTheme(theme);savePreference('cs2-report-theme',theme)};
for(const input of document.querySelectorAll('[data-match]')){input.checked=loadPreference(storageKey+':'+input.dataset.match,'false')==='true';input.onchange=()=>savePreference(storageKey+':'+input.dataset.match,String(input.checked))}
function textNode(tag,text,className){const node=document.createElement(tag);node.textContent=text;if(className)node.className=className;return node}
function moment(time,title,description,death=false){const node=document.createElement('div');node.className='timeline-item'+(death?' death':'');node.append(textNode('span',time,'time'),textNode('strong',title),textNode('small',description));return node}
function selectCase(index,focus=false){
 selectedCase=index;const item=data.cases[index],r=item.record,first=r.events.find(e=>e.enemy);
 for(const input of document.querySelectorAll('[data-note]'))input.value=reviewNotes[r.id][input.dataset.note];
 for(const button of document.querySelectorAll('[data-case]')){const selected=Number(button.dataset.case)===index;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;if(selected&&focus)button.focus()}
 $('case-panel').setAttribute('aria-labelledby','case-tab-'+index);
 $('case-meta').textContent=r.map.replace('de_','').toUpperCase()+' / ROUND '+r.round+' / '+r.side+' / '+r.date;
 for(const field of ['heading','observation','question','interpretation','limit'])$('case-'+field).textContent=item[field];
 $('case-result').textContent='Round '+(r.win?'won':'lost')+' · context, not a verdict';
 const timeline=$('case-timeline');timeline.replaceChildren();
 timeline.append(moment('BEFORE CONTACT','5v5', 'Plan the next position and the other line before committing.'));
 timeline.append(moment(first.seconds.toFixed(2)+'s INTO ROUND','Opening kill → '+first.after.join('v'),first.attacker_name+' → '+first.victim_name));
 if(r.death){const gap=(r.death.tick-first.tick)/r.tickrate;timeline.append(moment('+'+gap.toFixed(2)+'s','Your death → '+r.death.after.join('v'),r.death.attacker_name+' → '+r.death.victim_name,true))}
 else timeline.append(moment('ROUND END','You survive', 'A contrast to investigate; route and equipment change the comparison.'));
 $('open-replay').setAttribute('aria-label','Open '+r.map.replace('de_','')+' round '+r.round+' in the recorded 2D replay');
}
for(const button of document.querySelectorAll('[data-case]')){button.onclick=()=>selectCase(Number(button.dataset.case));button.onkeydown=event=>{let next=selectedCase;if(event.key==='ArrowRight')next=(next+1)%data.cases.length;else if(event.key==='ArrowLeft')next=(next+data.cases.length-1)%data.cases.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=data.cases.length-1;else return;event.preventDefault();selectCase(next,true)}}
selectCase(0);
function sendCase(){if(!viewerReady||!pendingCase)return;const r=pendingCase.record,first=r.events.find(e=>e.enemy);$('replay-frame').contentWindow.postMessage({type:'coaching-seek',source:r.source,round:r.round,tick:Math.max(r.freeze,first.tick-r.tickrate*5)},'*')}
$('open-replay').onclick=()=>{pendingCase=data.cases[selectedCase];opener=document.activeElement;const r=pendingCase.record;$('replay-title').textContent=r.map.replace('de_','').toUpperCase()+' · Round '+r.round+' · '+r.date;$('replay-status').textContent='Preparing recorded replay…';$('replay-dialog').showModal();if(!$('replay-frame').srcdoc)$('replay-frame').srcdoc=JSON.parse($('viewer-data').textContent);else sendCase()};
function closeReplay(){if($('replay-dialog').open)$('replay-dialog').close();$('replay-frame').contentWindow?.postMessage({type:'coaching-pause'},'*');opener?.focus()}
$('close-replay').onclick=closeReplay;
$('replay-dialog').addEventListener('cancel',event=>{event.preventDefault();closeReplay()});
window.addEventListener('message',event=>{if(event.source!==$('replay-frame').contentWindow)return;if(event.data?.type==='coaching-ready'){viewerReady=true;sendCase()}else if(event.data?.type==='coaching-loaded')$('replay-status').textContent='Paused before the opening kill · use Play or the timeline to inspect the sequence.'});
function renderGames(term=''){
 const games=data.games.filter(g=>(g.date+' '+g.map+' '+g.source).toLowerCase().includes(term.toLowerCase()));$('game-count').textContent=games.length+' of '+data.games.length+' selected games';
 $('game-rows').replaceChildren(...games.map(g=>{const tr=document.createElement('tr');tr.append(textNode('td',g.date),textNode('td',g.map.replace('de_','')),textNode('td',String(g.eligible_rounds)));const td=document.createElement('td');td.append(textNode('div',g.source,'source-name'));const details=document.createElement('details');details.append(textNode('summary','Demo hash, input hashes & '+g.warnings.length+' integrity warnings'));details.append(textNode('pre',JSON.stringify({demo_sha256:g.sha,schema:g.schema,inputs:g.inputs,warnings:g.warnings,excluded_rounds:g.excluded_rounds},null,2)));td.append(details);tr.append(td);return tr}));
}
$('game-search').oninput=event=>renderGames(event.target.value);renderGames();
