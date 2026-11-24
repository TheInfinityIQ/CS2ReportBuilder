/* Focused checks for personal notes; does not re-analyze any matches. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
(async()=>{
 const report=path.resolve(process.argv[2]||'reports/CanadianIQ/Coaching-Report.html');
 const out=path.join(path.dirname(report),'verification');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true,downloadsPath:out});const errors=[],network=[];
 try{
  const page=await browser.newPage({viewport:{width:1280,height:1000},acceptDownloads:true});
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url())});
  await page.goto(pathToFileURL(report).href);
  const original=await page.locator('#report-data').textContent(),data=JSON.parse(original);
  const openNotebook=async()=>{await page.locator('#analyst-desk').evaluate(e=>e.open=true);await page.locator('.evidence-tools').evaluate(e=>e.open=true);await page.locator('#review-notebook>summary').click()};
  await openNotebook();
  const note='QA fixture only: unknown call\n</textarea><script>window.noteInjected=true</script> “next action”';
  await page.locator('#note-information').fill(note);
  await page.locator('#note-plan').fill('QA fixture only: inspect whether a feasible alternative existed.');
  await page.locator('[data-case="1"]').click();assert.equal(await page.locator('#note-information').inputValue(),'');
  await page.locator('#note-adjustment').fill('QA fixture only: do not judge by outcome.');
  await page.reload();await openNotebook();
  assert.equal(await page.locator('#note-information').inputValue(),note);
  await page.locator('[data-case="1"]').click();assert.match(await page.locator('#note-adjustment').inputValue(),/do not judge/);
  await page.locator('[data-match="1"]').check();
  const downloadPromise=page.waitForEvent('download');await page.locator('#export-notes').click();const download=await downloadPromise;
  const exported=JSON.parse(await page.locator('#notes-export-text').inputValue());
  const downloadFailure=await download.failure();
  await page.locator('#select-export').click();
  assert.equal(await page.locator('#notes-export-text').evaluate(e=>e.selectionEnd-e.selectionStart),JSON.stringify(exported,null,2).length);
  assert.equal(download.suggestedFilename(),'CS2-review-'+data.player.steamid+'.json');
  assert.equal(exported.evidenceDigest,data.digest);assert.equal(exported.player.steamid,data.player.steamid);
  assert.equal(exported.situations.length,4);assert.equal(exported.situations[0].notes.information,note);
  assert.equal(exported.situations[0].demoSha256,data.cases[0].record.sha);
  assert.equal(exported.situations[0].roundId,data.cases[0].record.id);
  assert.equal(exported.situations[0].openingTick,data.cases[0].record.events.find(e=>e.enemy).tick);
  assert.equal(exported.practiceMatches[0].reviewed,true);
  assert.equal(await page.locator('#report-data').textContent(),original);
  assert.equal(await page.evaluate(()=>window.noteInjected),undefined);
  await page.evaluate(()=>localStorage.removeItem(storageKey+':notes'));await page.reload();
  await openNotebook();
  for(const theme of ['dark','light']){
   await page.evaluate(t=>setTheme(t),theme);await page.locator('#review-notebook').screenshot({path:path.join(out,'notebook-'+theme+'.png')});
  }
  await page.setViewportSize({width:768,height:1050});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.locator('#review-notebook').screenshot({path:path.join(out,'notebook-tablet.png')});
  await page.evaluate(()=>{localStorage.setItem(storageKey+':notes','damaged json')});await page.reload();
  await openNotebook();assert.equal(await page.locator('#note-information').inputValue(),'');
  await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw new DOMException('Storage blocked','QuotaExceededError')}});
  await page.reload();await openNotebook();
  await page.locator('#note-plan').fill('QA fixture only: memory survives changing situations.');
  assert.match(await page.locator('#notes-status').innerText(),/storage is unavailable/);
  await page.locator('[data-case="1"]').click();await page.locator('[data-case="0"]').click();
  assert.match(await page.locator('#note-plan').inputValue(),/memory survives/);
  const memoryDownloadPromise=page.waitForEvent('download');await page.locator('#export-notes').click();
  await memoryDownloadPromise;
  const memoryCopy=JSON.parse(await page.locator('#notes-export-text').inputValue());
  assert.match(memoryCopy.situations[0].notes.plan,/memory survives/);
  assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
  const result={notesIsolatedByRound:true,reloadPersistence:true,anchoredCopyableExport:true,downloadFailure,storageFailureExport:true,corruptStorageRecovery:true,evidenceUnchanged:true,themes:2,tabletLayout:true,errors,network};
  fs.writeFileSync(path.join(out,'notebook-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
