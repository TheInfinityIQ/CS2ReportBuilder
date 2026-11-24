'use strict';
const assert = require('node:assert/strict');
const {sameNetwork, frames} = require('./demo_compat.cjs');
const {BitWriter} = require('./vendor/faceit_demo_fixer/demofix.cjs')._internal;
function variable(n) { const a=[]; do { const b=n%128; n=Math.floor(n/128); a.push(b|(n?128:0)); } while(n); return Buffer.from(a); }
function packet(messages) {
  const writer=new BitWriter(1024);
  for (const [type,body] of messages) {writer.ubitvar(type);writer.varint32(body.length);writer.bytes(body);}
  const bytes=writer.finish();return Buffer.concat([Buffer.from([26]),variable(bytes.length),bytes]);
}
const entity=Buffer.from([1,2,3,4]), update=Buffer.from([8,5]);
const original=packet([[45,update],[55,entity],[207,Buffer.from('game event')]]);
const fixed=packet([[55,entity],[207,Buffer.from('game event')]]);
assert.doesNotThrow(()=>sameNetwork(original,fixed,7,new Set([5])));
assert.throws(()=>sameNetwork(original,fixed,7,new Set([6])),/Gameplay network messages changed/);
assert.throws(()=>sameNetwork(original,packet([[55,Buffer.from([1,2,3,5])],[207,Buffer.from('game event')]]),7,new Set([5])),/Gameplay network messages changed/);
assert.throws(()=>sameNetwork(original,packet([[55,entity],[207,Buffer.from('changed event')]]),7,new Set([5])),/Gameplay network messages changed/);
assert.throws(()=>frames(Buffer.from('bad demo')),/Not a CS2 demo/);
console.log('5 structural-preservation checks passed.');
