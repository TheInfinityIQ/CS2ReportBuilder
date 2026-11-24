const assert = require('node:assert/strict');
const test = require('node:test');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const {canonical, parseLaunch} = require('./CS2Toolbox.user.js');

test('pairing accepts only valid short-lived loopback settings', () => {
  assert.deepEqual(parseLaunch('#cs2toolbox=1&port=12345&pair=' + 'a'.repeat(43)), {port:12345, token:'a'.repeat(43)});
  assert.equal(parseLaunch('#ordinary-site-fragment'), null);
  for (const fragment of ['#cs2toolbox=2&port=12345&pair=' + 'a'.repeat(43),
    '#cs2toolbox=1&port=80&pair=' + 'a'.repeat(43), '#cs2toolbox=1&port=12345&pair=short']) {
    assert.throws(() => parseLaunch(fragment));
  }
});

test('URL matching preserves filters and rejects foreign hosts', () => {
  assert.equal(canonical('https://hltv.org/results?team=1&offset=100#ignored'), 'https://www.hltv.org/results?offset=100&team=1');
  assert.notEqual(canonical('https://hltv.org/results?team=1'), canonical('https://hltv.org/results?team=2'));
  for (const value of ['http://hltv.org/results', 'https://hltv.org.evil.test/results', 'https://hltv.org:8766/results', 'https://user:pass@hltv.org/results'])
    assert.throws(() => canonical(value));
});

test('FACEIT waits another 500ms before claiming/clicking and never clicks twice', async () => {
  const source = readFileSync(require.resolve('./CS2Toolbox.user.js'), 'utf8');
  const task = {id:'task-id', mode:'download', status:'pending', url:'https://www.faceit.com/en/cs2/room/1-12345678-1234-1234-1234-123456789abc'};
  let clicks = 0, claims = 0, tick, settle, acknowledgements = 0;
  const element = () => ({style:{}, append(){}, textContent:'', getClientRects:()=>[{}]});
  const watch = {...element(), textContent:'WATCH DEMO', disabled:false,
    closest:()=>null, getAttribute:()=>null, scrollIntoView(){}, click(){clicks++;}};
  const store = new Map();
  const location = new URL(task.url + '#cs2toolbox=1&port=12345&pair=' + 'a'.repeat(43));
  location.assign = () => { throw Error('Unexpected navigation'); };
  const document = {createElement:element, body:{append(){}}, querySelector:()=>null,
    querySelectorAll:selector=>selector === 'section strong' ? [] : [watch]};
  Object.defineProperty(document, 'cookie', {get(){throw Error('Cookies must never be read');}});
  const context = {
    URL, URLSearchParams, Date, JSON, Error, Number, String, Set, Map, location, document,
    sessionStorage:{getItem:key=>store.get(key), setItem:(key,value)=>store.set(key,value), removeItem:key=>store.delete(key)},
    crypto:{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'},
    history:{replaceState(){}}, getComputedStyle:()=>({visibility:'visible'}),
    setInterval:callback=>{tick=callback;},
    setTimeout(callback, delay) { assert.equal(delay, 500); settle = callback; },
    GM_xmlhttpRequest(options) {
      const route = new URL(options.url).pathname;
      if (route === '/state') options.onload({status:200, responseText:JSON.stringify({task})});
      else if (route === '/claim') {
        claims++;
        assert.equal(task.status, 'pending');
        task.status = 'claimed';
        options.onload({status:200, responseText:'{"ok":true,"acknowledge_click":true}'});
      } else if (route === '/clicked') {
        assert.equal(clicks, 1);acknowledgements++;
        options.onload({status:200, responseText:'{"ok":true}'});
      } else throw Error('Unexpected helper route: ' + route);
    },
  };
  vm.runInNewContext(source, context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(typeof settle, 'function');
  assert.equal(claims, 0);
  assert.equal(clicks, 0);
  await tick(); // Polling during the settling delay must not start another click.
  settle();
  await new Promise(resolve=>setImmediate(resolve));
  await tick();
  await tick();
  assert.equal(claims, 1);
  assert.equal(clicks, 1);
  assert.equal(acknowledgements, 1);
});

test('retry refreshes once, waits three seconds, and honors a late-download veto', async () => {
  const source = readFileSync(require.resolve('./CS2Toolbox.user.js'), 'utf8');
  const task = {id:'retry-id', mode:'download', status:'pending', attempt:2, reload:true,
    url:'https://www.faceit.com/en/cs2/room/1-12345678-1234-1234-1234-123456789abc'};
  let now=0, tick, settle, clicks=0, claims=0, reloads=0;
  const store=new Map();
  const element=()=>({style:{},append(){},textContent:'',getClientRects:()=>[{}]});
  const watch={...element(),textContent:'WATCH DEMO',closest:()=>null,getAttribute:()=>null,
    scrollIntoView(){},click(){clicks++;}};
  const location=new URL(task.url+'#cs2toolbox=1&port=12345&pair='+'a'.repeat(43));
  location.reload=()=>{reloads++;};
  const document={createElement:element,body:{append(){}},querySelector:()=>null,
    querySelectorAll:selector=>selector==='section strong'?[]:[watch]};
  vm.runInNewContext(source,{
    URL,URLSearchParams,Date:{now:()=>now},JSON,Error,Number,String,Set,Map,location,document,
    sessionStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
    crypto:{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'},history:{replaceState(){}},
    getComputedStyle:()=>({visibility:'visible'}),setInterval:fn=>{tick=fn;},
    setTimeout(fn,delay){assert.equal(delay,500);settle=fn;},
    GM_xmlhttpRequest(options){
      const body=JSON.parse(options.data);assert.ok(body.capabilities.includes('download-retry-v1'));
      const route=new URL(options.url).pathname;
      if(route==='/state')options.onload({status:200,responseText:JSON.stringify({task})});
      else if(route==='/claim'){claims++;task.status='download_observed';options.onload({status:200,responseText:'{"ok":true,"click":false}'});}
      else throw Error('Unexpected route: '+route);
    },
  });
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(reloads,1);
  await tick();now=2999;await tick();
  assert.equal(settle,undefined);assert.equal(claims,0);
  now=3000;const pending=tick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(typeof settle,'function');settle();await pending;
  assert.equal(reloads,1);assert.equal(claims,1);assert.equal(clicks,0);
});
