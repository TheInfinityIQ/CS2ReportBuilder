import test from 'node:test';
import assert from 'node:assert/strict';
import {interpolate, stateAt, smokeOpacity, weaponKey, upperBound, entityStatesAt, jumpAnimations, jumpAmount, crouchAmount} from './engine.mjs';

const sample=(tick,z,flags=0)=>[tick,0,0,z,0,0,flags];
const jumpTrack=[sample(0,100),sample(4,111,8),sample(8,126,8),sample(12,137,8),sample(16,145,8),sample(20,151,8),sample(24,155,8),sample(28,156,8),sample(32,154,8),sample(36,148,8),sample(40,139,8),sample(44,127,8),sample(48,112,8),sample(52,100)];

test('grounded ramps, stair steps, ledge drops and constant-speed elevation changes do not scale',()=>{
  const cases=[Array.from({length:15},(_,i)=>sample(i*4,i*18)),
    [sample(0,100),sample(4,118,8),sample(8,118)],
    [sample(0,100),...Array.from({length:8},(_,i)=>sample((i+1)*4,100-i*i*4,8)),sample(36,-156)],
    [sample(0,0),...Array.from({length:8},(_,i)=>sample((i+1)*4,(i+1)*12,8)),sample(36,108)]];
  for(const track of cases)assert.deepEqual(jumpAnimations(track),[]);
});

test('the same jump on different floors has identical scale and smooth endpoints',()=>{
  const animations=jumpAnimations(jumpTrack),shifted=jumpAnimations(jumpTrack.map(p=>p.map((v,i)=>i===3?v+1200:v)));
  assert.equal(animations.length,1);assert.deepEqual(animations,shifted);
  const {start,end}=animations[0];
  assert.equal(jumpAmount(animations,start),0);assert.equal(jumpAmount(animations,end),0);
  assert.equal(jumpAmount(animations,(start+end)/2),1);
  assert.ok(jumpAmount(animations,start+.01)<.00001);
  assert.ok(jumpAmount(animations,end-.01)<.00001);
  const a=jumpAmount(animations,18.3);jumpAmount(animations,45);assert.equal(jumpAmount(animations,18.3),a);
});

test('landing on a higher platform returns to normal size without inheriting its height',()=>{
  const track=[...jumpTrack.slice(0,6),sample(24,155)];
  const animations=jumpAnimations(track);assert.equal(animations.length,1);
  assert.equal(jumpAmount(animations,24),0);assert.ok(jumpAmount(animations,23.99)<.00001);
});

test('recorded jump events can confirm a short takeoff, but missing samples are not bridged',()=>{
  const short=[sample(0,0),sample(4,8,8),sample(8,12,8),sample(12,10)];
  assert.equal(jumpAnimations(short).length,0);
  assert.equal(jumpAnimations(short,64,[3]).length,1);
  assert.equal(jumpAnimations([sample(0,0),sample(100,10,8),sample(104,30,8),sample(108,20)],64,[100]).length,0);
});

test('crouch scale interpolates smoothly between samples',()=>{
  const track=[sample(0,0),sample(4,0,4)];
  assert.equal(crouchAmount(track,0),0);assert.equal(crouchAmount(track,2),.5);assert.equal(crouchAmount(track,4),1);
});

test('a jump followed by a long fall does not stay enlarged until the ground',()=>{
  const track=[...jumpTrack.slice(0,-1),sample(52,90,8),sample(56,70,8),sample(60,45,8),sample(64,15,8),sample(68,-20,8),sample(72,-60,8),sample(76,-100)];
  const animations=jumpAnimations(track);
  assert.equal(animations.length,1);
  assert.ok(animations[0].end<68);
  assert.equal(jumpAmount(animations,68),0);
});

test('recorded utility updates, removal and backward seeking use only the requested tick',()=>{
  const rows=[{tick:10,id:'1',action:'upsert',state:{burning:true}},
    {tick:20,id:'1',action:'upsert',state:{burning:false}},
    {tick:30,id:'1',action:'removed'}];
  assert.equal(entityStatesAt(rows,35).size,0);
  assert.equal(entityStatesAt(rows,25).get('1').burning,false);
  assert.equal(entityStatesAt(rows,15).get('1').burning,true);
  assert.equal(entityStatesAt(rows,9).size,0);
});

test('interpolation crosses north through the short arc and preserves discrete flags', () => {
  const p=interpolate([[0,0,0,0,179,0,0],[4,40,20,80,-179,10,8]],2);
  assert.equal(p.x,20);assert.equal(p.z,40);assert.equal(p.yaw,180);assert.equal(p.flags,0);
  assert.equal(interpolate([[10,0,0,0,0,0,0]],9),null);
});
test('seeking backward does not retain a later health or weapon state', () => {
  const player={states:[{tick:10,health:100,weapon:'ak47'},{tick:20,health:42,weapon:'knife'}]};
  assert.equal(stateAt(player,22).health,42);
  assert.equal(stateAt(player,12).health,100);assert.equal(stateAt(player,12).weapon,'ak47');
  assert.equal(upperBound([[1],[2],[2],[3]],2),3);
});
test('illustrative fallback HE hole is temporary and restores before expiry', () => {
  assert.ok(smokeOpacity(5,20,1,true).hole>.5);
  assert.equal(smokeOpacity(9,20,4,true).hole,0);
  assert.equal(smokeOpacity(5,20,1,false).hole,0);
  assert.equal(smokeOpacity(21,20,4,true).envelope,0);
});
test('display names resolve to existing asset conventions', () => {
  assert.equal(weaponKey('M4A1-S'),'m4a1_silencer');
  assert.equal(weaponKey('Smoke Grenade'),'smokegrenade');
  assert.equal(weaponKey('Bowie Knife'),'knife');
  assert.equal(weaponKey('SSG 08'),'ssg08');
});
