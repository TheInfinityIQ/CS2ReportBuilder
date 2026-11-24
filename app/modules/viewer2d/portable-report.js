// Runs only inside an exported HTML file. All payloads and images are embedded.
const reportWorkerURL=URL.createObjectURL(new Blob([reportWorker],{type:'text/javascript'}));
const reportHeatWorker=new Worker(reportWorkerURL);
URL.revokeObjectURL(reportWorkerURL);
let reportMessageId=0;const reportPending=new Map(),reportRoundCache=new Map();
function reportMessage(message){
  return new Promise((resolve,reject)=>{
    const id=++reportMessageId;reportPending.set(id,{resolve,reject});reportHeatWorker.postMessage({...message,id});
  });
}
reportHeatWorker.onmessage=({data})=>{
  const pending=reportPending.get(data.id);if(!pending)return;
  if(data.progress){
    const status=document.querySelector('#heat-status');
    if(status)status.textContent=`Averaging movement: ${data.progress.completed}/${data.progress.total} games`;
    return;
  }
  reportPending.delete(data.id);data.error?pending.reject(Error(data.error)):pending.resolve(data.value);
};
reportHeatWorker.onerror=()=>{
  for(const pending of reportPending.values())pending.reject(Error('The offline heat map worker could not start. Reopen this report in Chrome or Edge.'));
  reportPending.clear();
};
globalThis.heatmapProvider={
  context:source=>reportMessage({kind:'context',source}),
  compute:request=>reportMessage({kind:'compute',request}),
  cancel:()=>{
    reportHeatWorker.postMessage({kind:'cancel'});
    for(const pending of reportPending.values())pending.reject(Error('Superseded heat map request.'));
    reportPending.clear();
  }
};
globalThis.replayProvider={
  asset:path=>reportAssets[path]||(path.startsWith('weapons/')?reportAssets['weapons/knife.svg']:''),
  matches:()=>reportManifest.games,
  initial:()=>({source:reportManifest.games[0].source,round:reportManifest.games[0].rounds[0]}),
  watch(source,tick){
    const game=reportManifest.games.find(g=>g.source===source);
    if(!game?.nativeWatch||!Number.isSafeInteger(tick)||tick<0)throw Error('Rebuild this report to enable CS2 links for this recording.');
    location.href='cs2toolbox://watch?'+new URLSearchParams({demo:game.sha,tick:String(tick)});
  },
  async load(source,round){
    const game=reportManifest.games.find(g=>g.source===source);if(!game)throw Error('Game is outside this report.');
    if(round===null)round=game.rounds[0];
    const key=source+'\n'+round;
    if(reportRoundCache.has(key))return structuredClone(reportRoundCache.get(key));
    const encoded=reportPackets[source]?.[round];if(!encoded)throw Error('Round is outside this report.');
    const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
    const value=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
    if(value.source!==source||value.provenance.demoSha256!==game.sha)throw Error('Report replay identity mismatch.');
    reportRoundCache.set(key,value);while(reportRoundCache.size>2)reportRoundCache.delete(reportRoundCache.keys().next().value);
    return structuredClone(value);
  }
};
