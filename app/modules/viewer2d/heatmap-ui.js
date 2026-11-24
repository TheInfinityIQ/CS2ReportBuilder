// Static heat overlay. Network preparation and averaging run in the server worker;
// portable exports can supply the same provider contract without changing this UI.
export class HeatmapUI {
  constructor(stage) {
    this.generation=0;this.selected=new Set();this.opponents=new Set();this.enabled=false;
    this.root=document.createElement('details');this.root.className='heatmap-panel';
    this.root.innerHTML=`<summary>Heat map</summary><div class="heatmap-controls">
      <label><input id="heat-enabled" type="checkbox"> Heat map</label>
      <label>Seconds <output id="heat-seconds-value">40</output><input id="heat-seconds" type="range" min="1" max="120" step="1" value="40"></label>
      <label><input id="heat-cutoff" type="checkbox" checked> Cut off after first kill / death</label>
      <label>Map <span id="heat-map"></span></label>
      <label>Scope <select id="heat-game" aria-label="Heat map game"></select></label>
      <label>Side <select id="heat-side" aria-label="Heat map side"><option value="both">Both CT and T halves</option><option value="CT">CT half (includes overtime)</option><option value="T">T half (includes overtime)</option></select></label>
      <div id="heat-opponents"></div><div id="heat-players"></div>
      <button id="heat-reset" type="button">Reset heat map defaults</button>
      <div class="heat-legend"><span>CT blue</span><span>T orange</span><span>Dim → bright: repeated route entries</span></div>
      <small>Static opening summary · All-level projection · identical intensity scale across filters</small>
      <p id="heat-status" role="status" aria-live="polite">Enable heat map to prepare movement.</p>
    </div>`;
    stage.insertBefore(this.root,stage.querySelector('#ct-team'));
    this.$=id=>this.root.querySelector('#heat-'+id);
    this.$('enabled').onchange=()=>{this.enabled=this.$('enabled').checked;this.schedule(0)};
    this.$('seconds').oninput=()=>{this.$('seconds-value').value=this.$('seconds').value;this.schedule(250)};
    this.$('cutoff').onchange=this.$('side').onchange=()=>this.schedule(0);
    this.$('game').onchange=()=>{this.roster();this.schedule(0)};
    this.$('reset').onclick=()=>{
      this.$('seconds').value=40;this.$('seconds-value').value=40;this.$('cutoff').checked=true;
      this.$('side').value='both';this.$('game').value='all';
      this.selected=new Set((this.context?.players||[]).map(p=>p.id));
      this.opponents=new Set((this.context?.opponents||[]).map(p=>p.id));this.roster();this.schedule(0);
    };
  }
  async post(path,body){
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!response.ok)throw Error(`Heat map request failed (${response.status}).`);
    return response.json();
  }
  invalidate(){
    this.generation++;clearTimeout(this.timer);this.result=null;this.images=null;
    this.abort?.abort();
    globalThis.heatmapProvider?.cancel?.();
    if(this.job){this.post('/api/heatmap/cancel',{job:this.job}).catch(()=>{});this.job=null}
  }
  async setSource(replay){
    if(this.source===replay.source)return;
    this.invalidate();this.source=replay.source;this.context=null;
    this.$('map').textContent=replay.map.replace('de_','');this.$('status').textContent='Checking heat map identity…';
    this.$('enabled').disabled=true;const generation=this.generation;
    try{
      const provider=globalThis.heatmapProvider;
      const response=provider?null:await fetch('/api/heatmap/context?source='+encodeURIComponent(this.source));
      if(response&&!response.ok)throw Error('Heat map needs the local viewer server or a heat-enabled portable export.');
      const context=provider?await provider.context(this.source):await response.json();
      if(generation!==this.generation)return;
      this.context=context;
      if(!context.available){this.$('status').textContent=context.reason;this.$('players').replaceChildren();this.$('opponents').replaceChildren();return}
      this.selected=new Set(context.players.map(p=>p.id));this.opponents=new Set(context.opponents.map(o=>o.id));
      this.$('game').replaceChildren(this.option('all','All games on this map'),...context.games.map(g=>this.option(g.source,g.name)));
      this.$('enabled').disabled=false;this.roster();this.schedule(0);
    }catch(error){if(generation===this.generation)this.$('status').textContent=error.message}
  }
  option(value,label){const o=document.createElement('option');o.value=value;o.textContent=label;return o}
  checkbox(label,checked,onchange){
    const row=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=checked;
    input.onchange=()=>onchange(input.checked);row.append(input,document.createTextNode(label));return {row,input};
  }
  roster(){
    const context=this.context;if(!context?.available)return;
    const specific=context.games.find(g=>g.source===this.$('game').value);
    const opponentRoot=this.$('opponents');opponentRoot.replaceChildren();
    if(context.mode==='team'){
      const all=this.checkbox('All opponents',this.opponents.size===context.opponents.length,value=>{
        this.opponents=new Set(value?context.opponents.map(o=>o.id):[]);this.roster();this.schedule(0)});
      all.input.indeterminate=this.opponents.size>0&&this.opponents.size<context.opponents.length;opponentRoot.append(all.row);
      for(const o of context.opponents){const c=this.checkbox(`${o.name} · ${o.games??'?'} games`,this.opponents.has(o.id),value=>{
        value?this.opponents.add(o.id):this.opponents.delete(o.id);this.roster();this.schedule(0)});opponentRoot.append(c.row)}
    }
    const root=this.$('players');root.replaceChildren();
    const activeOpponents=new Set(context.players.flatMap(p=>Object.entries(p.coverage||{})
      .filter(([game,c])=>(!specific||game===specific.game)&&this.opponents.has(c.opponent))
      .map(([,c])=>c.opponent)));
    const opponentName=activeOpponents.size===1?context.opponents.find(o=>activeOpponents.has(o.id))?.name:'Opponents';
    const players=context.players.map(p=>{
      const eligible=Object.entries(p.coverage||{}).filter(([game,c])=>(!specific||game===specific.game)&&
        (context.mode==='player'||this.opponents.has(c.opponent)));
      return {...p,eligibleGames:eligible.length,eligibleRounds:eligible.reduce((n,[,c])=>n+c.rounds,0)};
    }).filter(p=>p.eligibleGames>0);
    for(const group of context.mode==='player'?['Tracked player']:['Team A','Opponents']){
      const members=players.filter(p=>context.mode==='player'||p.group===group);
      if(context.mode==='team'){
        const count=members.filter(p=>this.selected.has(p.id)).length;
        const heading=this.checkbox(group==='Team A'?context.teamName:opponentName||'Opponents',count===members.length&&members.length>0,value=>{
          for(const p of members)value?this.selected.add(p.id):this.selected.delete(p.id);this.roster();this.schedule(0)});
        heading.input.indeterminate=count>0&&count<members.length;heading.input.disabled=!members.length;root.append(heading.row);
      }
      for(const p of members){
        const c=this.checkbox(`${p.names.join(' / ')} · ${p.eligibleGames} games / ${p.eligibleRounds} rounds`,this.selected.has(p.id),value=>{
          value?this.selected.add(p.id):this.selected.delete(p.id);this.roster();this.schedule(0)});
        c.input.dataset.playerId=p.id;root.append(c.row);
      }
    }
  }
  schedule(delay){
    this.invalidate();
    if(!this.enabled){this.$('status').textContent='Heat map is off.';return}
    if(!this.context?.available){this.$('status').textContent=this.context?.reason||'Heat map identity unavailable.';return}
    const generation=this.generation;this.$('status').textContent='Preparing movement…';
    this.timer=setTimeout(()=>this.compute(generation),delay);
  }
  async compute(generation){
    const request={source:this.source,seconds:Number(this.$('seconds').value),cutoff:this.$('cutoff').checked,
      side:this.$('side').value,game:this.$('game').value,players:[...this.selected],opponents:[...this.opponents]};
    if(this.context.mode==='player'){
      // Defense in depth; the provider also rejects all non-tracked identities.
      request.players=request.players.filter(id=>id===this.context.tracked);request.opponents=[];
    }
    try{
      let result;
      if(globalThis.heatmapProvider){
        result=await globalThis.heatmapProvider.compute(request);
      }else{
        const submitted=await this.post('/api/heatmap',request);
        if(generation!==this.generation){this.post('/api/heatmap/cancel',{job:submitted.job}).catch(()=>{});return}
        this.job=submitted.job;
        for(;;){
          this.abort=new AbortController();
          const response=await fetch('/api/heatmap/status?job='+this.job,{signal:this.abort.signal});
          if(!response.ok)throw Error('Heat map job unavailable. Change a control to retry.');
          const status=await response.json();if(generation!==this.generation)return;
          if(status.status==='complete'){result=status.result;this.job=null;break}
          if(['error','cancelled'].includes(status.status))throw Error(status.error||'Heat map cancelled.');
          this.$('status').textContent=`${status.phase}: ${status.completed}/${status.total} games`;
          await new Promise(resolve=>setTimeout(resolve,150));if(generation!==this.generation)return;
        }
      }
      if(generation!==this.generation)return;
      this.result=result;this.prepareImages();
      const ct=result.samples.CT,t=result.samples.T;
      const exclusions=Object.entries(result.exclusions||{}).map(([key,n])=>`${n} ${key.replaceAll('_',' ')}`);
      if(result.excludedGames?.length)exclusions.push(`${result.excludedGames.length} games excluded: ${[...new Set(result.excludedGames)].join('; ')}`);
      this.$('status').textContent=`CT: ${ct.games} games / ${ct.rounds} rounds · T: ${t.games} games / ${t.rounds} rounds.`+
        (exclusions.length?' Excluded: '+exclusions.join(', '):'')+
        (!ct.rounds&&!t.rounds?' No eligible movement windows.':'');
    }catch(error){if(generation===this.generation){this.result=null;this.images=null;this.$('status').textContent=error.message}}
  }
  prepareImages(){
    this.images={};const n=this.result.grid;
    for(const side of ['CT','T']){
      const canvas=document.createElement('canvas');canvas.width=canvas.height=n;
      const c=canvas.getContext('2d'),pixels=c.createImageData(n,n),rgb=side==='CT'?[70,160,255]:[255,157,48];
      const raw=this.result.layers[side];
      // Fixed 3x3 smoothing kernel; fixed scale, never normalize to a filtered max.
      for(let y=0;y<n;y++)for(let x=0;x<n;x++){
        let v=0;
        for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
          if(x+dx>=0&&x+dx<n&&y+dy>=0&&y+dy<n)v+=(raw[(y+dy)*n+x+dx]||0)*(dx===0?2:1)*(dy===0?2:1)/16;
        }
        const i=(y*n+x)*4;pixels.data.set(rgb,i);pixels.data[i+3]=Math.round(235*(1-Math.exp(-v/this.result.scale)));
      }
      c.putImageData(pixels,0,0);this.images[side]=canvas;
    }
  }
  draw(ctx,view){
    if(!this.enabled||!this.images)return;
    ctx.save();ctx.imageSmoothingEnabled=true;ctx.globalCompositeOperation='lighter';
    for(const side of ['CT','T'])ctx.drawImage(this.images[side],view.x,view.y,view.size,view.size);
    ctx.restore();
  }
}
