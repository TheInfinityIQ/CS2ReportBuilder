/* Reading-first contract: core value must survive disabled JavaScript and printing. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
function luminance(hex){const v=hex.trim().replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722}
(async()=>{
 const report=path.resolve(process.argv[2]||'reports/CanadianIQ/Coaching-Report.html'),out=path.join(path.dirname(report),'verification');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100},javaScriptEnabled:false});
  await page.goto(pathToFileURL(report).href);
  assert.equal(await page.locator('h1').innerText(),'CanadianIQ');
  assert.equal(await page.locator('.profile-facts>div').count(),3);
  assert.deepEqual(await page.locator('.insight-list>li').evaluateAll(items=>items.map(e=>e.className)),['insight positive','insight contextual','insight developing']);
  assert.equal(await page.locator('.reading-case').count(),4);
  assert.equal(await page.locator('.reading-case').first().getAttribute('data-reading-case'),'3');
  assert.equal(await page.locator('.reading-case').first().isVisible(),false);
  assert.equal(await page.locator('#analyst-desk .reading-case').count(),4);
  assert.equal(/\b(?:round|rounds)[ \t]+\d|\bR\d/i.test(await page.locator('main').innerText()),false,'specific rounds leaked into main narrative');
  for(const node of await page.locator('#insights .reading-cue p,.practice-grid article').all())assert.equal(await node.isVisible(),true);
  assert.equal(await page.locator('.evidence-tools').getAttribute('open'),null);
  const profileY=await page.locator('#focus').evaluate(e=>e.offsetTop),insightsY=await page.locator('#insights').evaluate(e=>e.offsetTop),practiceY=await page.locator('#practice').evaluate(e=>e.offsetTop);
  assert.ok(profileY<insightsY&&insightsY<practiceY);
  const measures=JSON.parse(await page.locator('#report-data').textContent()).measures;
  const reviewed=JSON.parse(await page.locator('#report-data').textContent());
  assert.equal(await page.locator('.situation-insight').count(),0);
  assert.deepEqual(reviewed.situation_insights,[]);
  assert.equal(reviewed.situation_review.dispositions.length,8);
  assert.equal(reviewed.theme_evidence.fast_maps,6);
  assert.equal(reviewed.theme_evidence.fast_games,19);
  await page.locator('#analyst-desk>summary').click();
  for(const m of measures)assert.equal(await page.locator('[data-measure="'+m.id+'"] td:nth-child(2)').innerText(),m.value.toLocaleString('en-US'));
  await page.locator('#analyst-desk').screenshot({path:path.join(out,'analyst-desk.png')});
  const ratios={};
  for(const theme of ['dark','light']){
   await page.locator('html').evaluate((e,t)=>e.dataset.theme=t,theme);
   const colors=await page.locator('html').evaluate(e=>Object.fromEntries(['bg','surface','text','muted','accent','amber'].map(k=>[k,getComputedStyle(e).getPropertyValue('--'+k)])));
   ratios[theme]={};for(const foreground of ['text','muted','accent','amber'])for(const background of ['bg','surface']){const a=luminance(colors[foreground]),b=luminance(colors[background]),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);ratios[theme][foreground+'/'+background]=Number(ratio.toFixed(2));assert.ok(ratio>=4.5,theme+' '+foreground+'/'+background+' contrast '+ratio)}
   await page.locator('.hero').screenshot({path:path.join(out,'profile-'+theme+'.png')});
   await page.locator('#insights').screenshot({path:path.join(out,'insights-'+theme+'.png')});
   await page.locator('.reading-case').first().screenshot({path:path.join(out,'reading-example-'+theme+'.png')});
  }
  await page.setViewportSize({width:768,height:1100});await page.locator('#insights').screenshot({path:path.join(out,'reading-tablet.png')});
  for(const width of [1024,768,390]){await page.setViewportSize({width,height:1100});assert.equal(await page.locator('html').evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'reading overflow at '+width)}
  await page.emulateMedia({media:'print'});
  assert.equal(await page.locator('html').evaluate(e=>getComputedStyle(e).getPropertyValue('--bg').trim()),'#fff');
  for(const node of await page.locator('.reading-case,.insight,.situation-insight,.practice-grid article').all())assert.equal(await node.isVisible(),true);
  const result={noJavaScriptReading:true,profileFirst:true,positivesFirst:true,mainNarrativeRoundFree:true,optionalEvidenceCases:4,practiceAfterInsights:true,analystDeskBindings:true,printNarrative:true,widths:[1440,1024,768,390],coreTextContrast:ratios};
  fs.writeFileSync(path.join(out,'presentation-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
