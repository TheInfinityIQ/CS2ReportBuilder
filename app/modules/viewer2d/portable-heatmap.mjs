// Offline counterpart of heatmap.py. Keep route/averaging semantics in parity.
export function passages(track,start,end,rate,calibration,ownDeath=null){
  if(ownDeath!==null)end=Math.min(end,ownDeath);
  const result=new Map();if(end<=start)return [result,false];
  let last=null,anchor=null,previous=null,observed=false;
  const distance=(a,b)=>Math.hypot(a[1]-b[1],a[2]-b[2],a[3]-b[3]);
  for(const point of track){
    const [t]=point;
    if(!previous){anchor=previous=point;continue}
    const dt=t-previous[0];
    if(!(dt>0&&dt<=rate*.5&&distance(previous,point)<=400*dt/rate+24)){
      anchor=previous=point;last=null;continue;
    }
    if(t>=start&&previous[0]<=end)observed=true;
    previous=point;
    if(distance(anchor,point)<12)continue;
    const a=anchor,b=point;anchor=point;
    const lo=Math.max(start,a[0]),hi=Math.min(end,b[0]);if(hi<=lo)continue;
    const f0=(lo-a[0])/(b[0]-a[0]),f1=(hi-a[0])/(b[0]-a[0]);
    const p=[1,2].map(i=>a[i]+(b[i]-a[i])*f0),q=[1,2].map(i=>a[i]+(b[i]-a[i])*f1);
    const {scale,pos_x:px,pos_y:py}=calibration;
    const u0=(p[0]-px)/scale/16,v0=(py-p[1])/scale/16,u1=(q[0]-px)/scale/16,v1=(py-q[1])/scale/16;
    const cuts=new Set([0,1]);
    for(const [x0,x1] of [[u0,u1],[v0,v1]])if(x1!==x0){
      for(let boundary=Math.floor(Math.min(x0,x1))+1;boundary<Math.ceil(Math.max(x0,x1));boundary++)cuts.add((boundary-x0)/(x1-x0));
    }
    const sorted=[...cuts].sort((a,b)=>a-b);
    for(let i=1;i<sorted.length;i++){
      const f=(sorted[i-1]+sorted[i])/2,x=Math.floor(u0+(u1-u0)*f),y=Math.floor(v0+(v1-v0)*f),key=x+','+y;
      if(key!==last){if(x>=0&&x<64&&y>=0&&y<64){const cell=y*64+x;result.set(cell,(result.get(cell)||0)+1)}last=key}
    }
  }
  return [result,observed];
}

function quality(round,selected){
  const tracks=round.players.filter(p=>selected.has(p.id)).map(p=>p.track);
  return [round.valid!==false,round.deaths_available!==false,tracks.filter(t=>t.length>1).length,tracks.reduce((n,t)=>n+t.length,0)];
}
function better(a,b){for(let i=0;i<a.length;i++){if(a[i]>b[i])return true;if(a[i]<b[i])return false}return false}

export function aggregate(games,selected,seconds=40,cutoff=true,side='both'){
  if(!Number.isInteger(seconds)||seconds<1||seconds>120||!['both','CT','T'].includes(side))throw Error('Invalid heat map timing or side.');
  const layers=new Map(),eligible=new Map(),excluded={},best=new Map(),seen=new Set();
  const exclude=(key,n=1)=>excluded[key]=(excluded[key]||0)+n;
  for(const game of games)for(const round of game.rounds){
    const key=game.game+'\n'+round.id,old=best.get(key);
    if(!old||better(quality(round,selected),quality(old,selected)))best.set(key,round);
  }
  for(const game of games){
    const sums={CT:new Float64Array(4096),T:new Float64Array(4096)},counts={CT:0,T:0};
    for(const rnd of game.rounds){
      const key=game.game+'\n'+rnd.id;
      if(seen.has(key)||best.get(key)!==rnd){exclude('duplicate_rounds');continue}seen.add(key);
      if(rnd.valid===false){exclude('invalid_rounds');continue}
      if(rnd.deaths_available===false){exclude('missing_death_stream');continue}
      const deaths=rnd.deaths.filter(d=>d.tick>=rnd.start&&d.tick<=rnd.end);
      const stop=Math.min(rnd.end,rnd.start+seconds*game.rate,...(cutoff?deaths.map(d=>d.tick):[]));
      const per={CT:new Float64Array(4096),T:new Float64Array(4096)},present=new Set(),unknown=new Set();
      for(const player of rnd.players){
        if(!selected.has(player.id)||!['CT','T'].includes(player.side))continue;
        const own=deaths.filter(d=>d.id===player.id).map(d=>d.tick);
        const [grid,observed]=passages(player.track,rnd.start,stop,game.rate,game.calibration,own.length?Math.min(...own):null);
        if(!observed){exclude('missing_player_windows');unknown.add(player.side);continue}
        present.add(player.side);for(const [cell,value] of grid)per[player.side][cell]+=value;
      }
      if(!present.size)exclude('absent_selection_rounds');
      for(const bucket of present)if(!unknown.has(bucket)){
        counts[bucket]++;for(let i=0;i<4096;i++)sums[bucket][i]+=per[bucket][i];
      }
    }
    if(!layers.has(game.game)){layers.set(game.game,{CT:new Float64Array(4096),T:new Float64Array(4096)});eligible.set(game.game,{CT:0,T:0})}
    for(const bucket of ['CT','T']){
      eligible.get(game.game)[bucket]+=counts[bucket];
      for(let i=0;i<4096;i++)layers.get(game.game)[bucket][i]+=sums[bucket][i];
    }
  }
  const output={},samples={};
  for(const bucket of ['CT','T']){
    const grid=new Float64Array(4096);let nGames=0,nRounds=0;
    for(const [key,game] of layers){
      const n=eligible.get(key)[bucket];if(!n)continue;nGames++;nRounds+=n;
      for(let i=0;i<4096;i++)grid[i]+=game[bucket][i]/n;
    }
    output[bucket]=Array.from(grid,v=>side==='both'||side===bucket?(nGames?v/nGames:v):0);
    samples[bucket]={games:nGames,rounds:nRounds};
  }
  return {version:'opening-passages-1',grid:64,layers:output,samples,exclusions:excluded,scale:.5,
    projection:'All-level projection',unit:'mean route entries per eligible round, equal weight per game'};
}

export function validateRequest(manifest,request){
  const anchor=manifest.games.find(g=>g.source===request.source);
  if(!anchor)throw Error('Game is not included in this report.');
  const context=manifest.contexts[anchor.map],allowed=new Set(context.players.map(p=>p.id));
  if(!Array.isArray(request.players)||request.players.some(id=>!allowed.has(id)))throw Error('Player is outside this report.');
  if(context.mode==='player'&&request.players.some(id=>id!==context.tracked))throw Error('Player reports are restricted to the tracked player.');
  if(!Array.isArray(request.opponents)||request.opponents.some(id=>!context.opponents.some(o=>o.id===id)))throw Error('Opponent is outside this report.');
  if(context.mode==='player'&&request.opponents.length)throw Error('Opponent filters are unavailable for player reports.');
  if(!Number.isInteger(request.seconds)||request.seconds<1||request.seconds>120||typeof request.cutoff!=='boolean'||!['both','CT','T'].includes(request.side))throw Error('Invalid heat map settings.');
  let entries=manifest.games.filter(g=>g.map===anchor.map);
  if(request.game!=='all'){
    const target=entries.find(g=>g.source===request.game);if(!target)throw Error('Game is outside this map.');
    entries=entries.filter(g=>g.game===target.game);
  }
  if(context.mode==='team')entries=entries.filter(g=>request.opponents.includes(g.opponent));
  return {entries,anchor};
}

export function installWorker(manifest,movement){
  let generation=0;const cache=new Map();
  async function decode(source){
    if(cache.has(source))return cache.get(source);
    const bytes=Uint8Array.from(atob(movement[source]),c=>c.charCodeAt(0));
    const value=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
    cache.set(source,value);while(cache.size>2)cache.delete(cache.keys().next().value);return value;
  }
  self.onmessage=async({data:message})=>{
    const current=++generation;
    try{
      if(message.kind==='cancel')return;
      if(message.kind==='context'){
        const game=manifest.games.find(g=>g.source===message.source);if(!game)throw Error('Unknown report game.');
        self.postMessage({id:message.id,value:manifest.contexts[game.map]});return;
      }
      const r=message.request,{entries,anchor}=validateRequest(manifest,r),groups=new Map();
      for(const entry of entries){if(!groups.has(entry.game))groups.set(entry.game,[]);groups.get(entry.game).push(entry)}
      const result=aggregate([],new Set(r.players),r.seconds,r.cutoff,r.side);let done=0;
      for(const copies of groups.values()){
        const prepared=[];for(const entry of copies){if(current!==generation)return;prepared.push(await decode(entry.source))}
        const single=aggregate(prepared,new Set(r.players),r.seconds,r.cutoff,r.side);
        for(const side of ['CT','T'])if(single.samples[side].rounds){
          result.samples[side].games++;result.samples[side].rounds+=single.samples[side].rounds;
          for(let i=0;i<4096;i++)result.layers[side][i]+=single.layers[side][i];
        }
        for(const [reason,n] of Object.entries(single.exclusions))result.exclusions[reason]=(result.exclusions[reason]||0)+n;
        self.postMessage({id:message.id,progress:{completed:++done,total:groups.size}});
        await new Promise(resolve=>setTimeout(resolve,0));if(current!==generation)return;
      }
      for(const side of ['CT','T'])if(result.samples[side].games)result.layers[side]=result.layers[side].map(v=>v/result.samples[side].games);
      result.map=anchor.map;result.excludedGames=[];
      if(current===generation)self.postMessage({id:message.id,value:result});
    }catch(error){self.postMessage({id:message.id,error:error.message})}
  };
}
