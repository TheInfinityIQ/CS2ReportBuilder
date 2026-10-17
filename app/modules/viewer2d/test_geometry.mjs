import test from 'node:test';
import assert from 'node:assert/strict';
import {fireMesh} from './geometry.mjs';
const point=(x,y,z=0,burning=true)=>({x,y,z,burning});
test('a square is tiled by two non-overlapping consistently wound faces',()=>{
  const m=fireMesh([point(0,0),point(40,0),point(40,40),point(0,40)]);
  assert.equal(m.triangles.length,2);
  const areas=m.triangles.map(face=>{const [a,b,c]=face.map(i=>m.points[i]);return ((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))/2;});
  assert.ok(areas.every(a=>a>0));assert.equal(areas.reduce((a,b)=>a+b,0),1600);
});
test('extinguished, distant and vertically separated patches do not bridge',()=>{
  assert.equal(fireMesh([point(0,0),point(40,0),point(0,40,100)]).triangles.length,0);
  const m=fireMesh([point(0,0),point(500,0),point(0,40,0,false)]);
  assert.equal(m.points.length,2);assert.equal(m.triangles.length,0);assert.equal(m.links.length,0);
});
test('sparse and collinear patches retain short links without degenerate faces',()=>{
  const m=fireMesh([point(0,0),point(30,0),point(60,0),point(0,0)]);
  assert.equal(m.points.length,3);assert.equal(m.triangles.length,0);assert.equal(m.links.length,3);
});
