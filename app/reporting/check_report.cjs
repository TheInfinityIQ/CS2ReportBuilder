/* Application-owned, bounded browser fixture for the generated offline report. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
(async()=>{
 const report=path.resolve(process.argv[2]||'reports/CanadianIQ/Coaching-Report.html'),out=path.join(path.dirname(report),'verification');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const errors=[],network=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100},reducedMotion:'reduce'});
  page.on('pageerror',error=>errors.push(error.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url())});
  await page.goto(pathToFileURL(report).href);
  const reportData=await page.evaluate(()=>JSON.parse(document.querySelector('#report-data').textContent));
  assert.equal(reportData.totals.games,50);assert.equal(reportData.totals.rounds,1134);assert.equal(reportData.excluded,8);
  assert.deepEqual(reportData.summary,{total:94,within2:12,twoToTen:13,later:32,survived:37});
  assert.equal(await page.locator('#game-rows tr').count(),50);
  assert.equal(await page.locator('#game-rows tr:first-child td:nth-child(3)').textContent(),String(reportData.games[0].eligible_rounds));
  await page.locator('.hero').screenshot({path:path.join(out,'hero-dark.png')});
  await page.locator('.signal').screenshot({path:path.join(out,'signal-dark.png')});
  await page.locator('#practice').screenshot({path:path.join(out,'practice-dark.png')});
  await page.locator('#evidence').screenshot({path:path.join(out,'evidence-dark.png')});
  await page.locator('#theme').click();assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  await page.locator('.hero').screenshot({path:path.join(out,'hero-light.png')});
  await page.locator('#evidence').screenshot({path:path.join(out,'evidence-light.png')});
  await page.locator('#theme').click();
  await page.locator('#analyst-desk>summary').click();
  await page.locator('.evidence-tools>summary').click();
  for(let i=0;i<4;i++){
   await page.locator('[data-case="'+i+'"]').click();
   assert.equal(await page.locator('[aria-selected="true"]').count(),1);
   assert.equal(await page.locator('#case-heading').innerText(),reportData.cases[i].heading);
   await page.locator('#open-replay').click();
   const r=reportData.cases[i].record;
   await page.waitForFunction(()=>document.querySelector('#replay-status').textContent.startsWith('Paused before'),null,{timeout:7000});
   const frame=page.frames().find(f=>f.url()==='about:srcdoc');assert.ok(frame,'embedded renderer exists');
   const state=await frame.evaluate(()=>({source:replay.source,round:replay.round,tick,players:replay.players.length,tracks:replay.players.every(p=>p.track.length),ready:mapReady}));
   assert.equal(state.source,r.source);assert.equal(state.round,r.round);assert.equal(state.players,10);assert.ok(state.tracks);
   const opening=r.events.find(e=>e.enemy);assert.equal(state.tick,Math.max(r.freeze,opening.tick-r.tickrate*5));
   await frame.waitForFunction(()=>mapReady,null,{timeout:7000});
   await frame.evaluate(t=>{seek(t);render()},opening.tick+3);
   if(i===0)await page.locator('#replay-dialog').screenshot({path:path.join(out,'replay-mirage.png')});
   if(i===2)await page.locator('#replay-dialog').screenshot({path:path.join(out,'replay-ancient.png')});
   await frame.locator('#play').click();assert.equal(await frame.evaluate(()=>playing),true);
   await page.locator('#close-replay').click();await page.waitForTimeout(50);assert.equal(await frame.evaluate(()=>playing),false);
  }
  await page.locator('[data-case="0"]').click();await page.locator('[data-case="0"]').focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('[data-case="1"]').getAttribute('aria-selected'),'true');
  await page.locator('.sources > summary').click();await page.locator('#game-search').fill('nuke');assert.equal(await page.locator('#game-rows tr').count(),2);await page.locator('#game-search').fill('no-such-game');assert.equal(await page.locator('#game-rows tr').count(),0);await page.locator('#game-search').fill('');await page.locator('.sources > summary').click();
  await page.locator('[data-match="1"]').check();await page.reload();assert.equal(await page.locator('[data-match="1"]').isChecked(),true);await page.locator('[data-match="1"]').uncheck();
  for(const width of [1024,768,390]){await page.setViewportSize({width,height:1050});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'no overflow at '+width);if(width===768){await page.locator('.hero').screenshot({path:path.join(out,'tablet-hero.png')});await page.locator('#evidence').screenshot({path:path.join(out,'tablet-evidence.png')})}}
  await page.setViewportSize({width:768,height:1050});await page.locator('#analyst-desk').evaluate(e=>e.open=true);await page.locator('.evidence-tools').evaluate(e=>e.open=true);await page.locator('#open-replay').click();
  await page.waitForFunction(()=>document.querySelector('#replay-status').textContent.startsWith('Paused before'),null,{timeout:7000});
  const tabletFrame=page.frames().find(f=>f.url()==='about:srcdoc');await tabletFrame.waitForFunction(()=>mapReady,null,{timeout:7000});
  assert.ok(await tabletFrame.locator('#map').evaluate(e=>e.getBoundingClientRect().width)>100);
  await page.locator('#replay-dialog').screenshot({path:path.join(out,'tablet-replay.png')});await page.locator('#close-replay').click();
  assert.deepEqual(network,[],'report must work without network');assert.deepEqual(errors,[]);
  const result={offline:true,games:50,rounds:1134,excludedRounds:8,examples:4,exactReplayNavigation:true,themes:2,widths:[1440,1024,768,390],keyboardTabs:true,checklistPersistence:true,sourceSearch:true,errors,network};
  fs.writeFileSync(path.join(out,'browser-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
