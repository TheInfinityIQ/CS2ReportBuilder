import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {directionEndpoint,prepareShots,comparisonShot} from './shots.mjs';

const origin=[10,20,30];
assert.deepEqual(directionEndpoint({origin,angles:[0,0]},100),[110,20,30]);
const north=directionEndpoint({origin,angles:[0,90]},100);
assert.ok(Math.abs(north[0]-10)<1e-9 && Math.abs(north[1]-120)<1e-9);
const down=directionEndpoint({origin,angles:[90,0]},100);
assert.ok(Math.abs(down[2]+70)<1e-9);
assert.equal(directionEndpoint({origin,angles:null}),null);
assert.equal(directionEndpoint({origin,angles:[NaN,0]}),null);

const replay=JSON.parse(readFileSync(new URL('./shot-check-round.json',import.meta.url)));
const before=JSON.stringify(replay.shots);
const shots=prepareShots(replay.shots,replay.events);
assert.equal(shots.length,151);
assert.ok(shots.every(s=>directionEndpoint(s) && s.impact===null));
assert.equal(JSON.stringify(replay.shots),before,'Preparing directions must not mutate source data or invent impacts');
const comparison=comparisonShot(shots,replay.tickrate);
assert.ok(comparison && comparison.tick>=replay.start && comparison.tick<=replay.end);
assert.equal(comparisonShot([],64),null);
console.log(`Shot comparison passed: ${shots.length} recorded shots have directions; no impacts fabricated.`);
