// Application-side adapter for the pinned MIT-licensed baseline repair.
// Never writes the input. No networking, telemetry, event-text sanitization,
// dependencies, or execution of console messages from a recording.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const fixer = require('./vendor/faceit_demo_fixer/demofix.cjs');
const ALLOWED = new Set(['instancebaseline', 'AnimAssetData']);
const equal = (a, b) => Buffer.from(a.buffer, a.byteOffset, a.byteLength).equals(Buffer.from(b.buffer, b.byteOffset, b.byteLength));
function requireTrue(ok, reason) { if (!ok) throw new Error(reason); }

function varint(data, cursor) {
  let value = 0, shift = 0;
  for (let i = 0; i < 10; i++, shift += 7) {
    requireTrue(cursor.at < data.length, 'Truncated varint');
    const b = data[cursor.at++]; value += (b & 127) * 2 ** shift;
    if (!(b & 128)) return value;
  }
  throw new Error('Oversized varint');
}
function fields(data) {
  const cursor = {at: 0}, result = [];
  while (cursor.at < data.length) {
    const start = cursor.at, key = varint(data, cursor), wire = key % 8, field = Math.floor(key / 8);
    let value;
    if (wire === 0) value = varint(data, cursor);
    else {
      const size = wire === 2 ? varint(data, cursor) : wire === 1 ? 8 : wire === 5 ? 4 : -1;
      requireTrue(size >= 0 && size <= data.length - cursor.at, 'Invalid protobuf field');
      value = data.subarray(cursor.at, cursor.at + size); cursor.at += size;
    }
    result.push({field, wire, value, raw: data.subarray(start, cursor.at)});
  }
  return result;
}
const get = (data, n) => fields(data).find(f => f.field === n)?.value;
const text = data => Buffer.from(data || []).toString('utf8');
function frames(data) {
  requireTrue(data.length >= 16 && text(data.subarray(0, 8)) === 'PBDEMS2\0', 'Not a CS2 demo');
  const cursor = {at: 16}, result = [];
  while (cursor.at < data.length) {
    const start = cursor.at, command = varint(data, cursor), tick = varint(data, cursor), size = varint(data, cursor);
    requireTrue(size <= data.length - cursor.at, 'Truncated demo frame');
    result.push({command, tick, start, data: data.subarray(cursor.at, cursor.at + size)}); cursor.at += size;
  }
  return result;
}
function payload(frame) {
  return frame.command & 64 ? fixer._internal.snappyUncompress(frame.data) : frame.data;
}
function inner(data) {
  const reader = new fixer._internal.BitReader(data), result = [];
  while (reader.left() > 8) {
    const type = reader.ubitvar(), size = reader.varint32();
    requireTrue(size * 8 <= reader.left(), 'Invalid network packet');
    result.push({type, data: reader.bytes(size)});
  }
  return result;
}
function sameFields(a, b, excluded) {
  const left = fields(a).filter(f => !excluded.has(f.field));
  const right = fields(b).filter(f => !excluded.has(f.field));
  requireTrue(left.length === right.length && left.every((f, i) => equal(f.raw, right[i].raw)), 'Unapproved protobuf change');
}
function sameTables(a, b) {
  const keep = data => fields(data).filter(f => f.field !== 1 || !ALLOWED.has(text(get(f.value, 1))));
  const left = keep(a), right = keep(b);
  requireTrue(left.length === right.length && left.every((f, i) => equal(f.raw, right[i].raw)), 'Unapproved table snapshot change');
}
function sameNetwork(a, b, command, tableIDs) {
  sameFields(a, b, new Set([3]));
  const keep = data => inner(get(data, 3) || new Uint8Array()).filter(message => {
    if (command === 8 && message.type === 44) return !ALLOWED.has(text(get(message.data, 1)));
    if (command === 7 && message.type === 45) return !tableIDs.has(get(message.data, 1) || 0);
    return true;
  });
  const left = keep(a), right = keep(b);
  requireTrue(left.length === right.length && left.every((m, i) => m.type === right[i].type && equal(m.data, right[i].data)),
    'Gameplay network messages changed');
}
function verify(original, corrected, report) {
  const left = frames(original), right = frames(corrected);
  requireTrue(left.length === right.length, 'Frame count changed');
  const tableIDs = new Set(); let tableNumber = 0;
  for (const frame of left) {
    if ((frame.command & ~64) === 7) break;
    if ((frame.command & ~64) !== 8) continue;
    for (const message of inner(get(payload(frame), 3) || new Uint8Array())) {
      if (message.type === 51) { tableNumber = 0; tableIDs.clear(); }
      if (message.type === 44) {
        if (ALLOWED.has(text(get(message.data, 1)))) tableIDs.add(tableNumber);
        tableNumber++;
      }
    }
  }
  let modified = 0;
  for (let i = 0; i < left.length; i++) {
    const a = left[i], b = right[i], command = a.command & ~64;
    requireTrue(a.command === b.command && a.tick === b.tick, 'Frame identity/timing changed');
    if (equal(a.data, b.data)) continue;
    modified++;
    const ap = payload(a), bp = payload(b);
    if (command === 8) sameNetwork(ap, bp, command, tableIDs);
    else if (command === 7 && a.tick === report.crashFix.firstPacketTick) sameNetwork(ap, bp, command, tableIDs);
    else if (command === 6) sameTables(ap, bp);
    else if (command === 13 && a.tick === report.crashFix.firstPacketTick) {
      sameFields(ap, bp, new Set([1]));
      sameTables(get(ap, 1) || new Uint8Array(), get(bp, 1) || new Uint8Array());
    } else throw new Error('Changed a frame outside the baseline repair scope');
  }
  requireTrue(modified === report.modifiedMessages, 'Unexpected modified frame count');
  for (const [offset, command] of [[8, 2], [12, 15]]) {
    const pointer = corrected.readUInt32LE(offset);
    if (pointer) requireTrue(right.some(f => f.start === pointer && (f.command & ~64) === command), 'Invalid rewritten header offset');
  }
  return {frames: left.length, modified_frames: modified, gameplay_messages_identical: true};
}

function main() {
  const [source, destination] = process.argv.slice(2);
  requireTrue(source && destination && path.resolve(source) !== path.resolve(destination), 'Distinct input/output paths required');
  const original = fs.readFileSync(source);
  requireTrue(original.length <= 1024 ** 3, 'This compatibility adapter is limited to 1 GiB recordings');
  const result = fixer.fixDemo(original, {sanitizeText: false});
  const report = result.report;
  const response = {source_sha256: crypto.createHash('sha256').update(original).digest('hex'), report};
  if (result.changed) {
    requireTrue(report.crashFix.needed && report.crashFix.applied && !report.warnings.length && !report.textFix.items.length,
      'Repair did not meet the narrow compatibility scope');
    const baseline = report.crashFix.tables.find(t => t.name === 'instancebaseline');
    requireTrue(baseline && baseline.added.length && baseline.added.every(e => e.className === 'CChicken') &&
      report.crashFix.tables.every(t => ALLOWED.has(t.name) && !t.replaced.length), 'Unsupported baseline repair pattern');
    requireTrue(result.size <= original.length + 16 * 1024 ** 2, 'Unexpected repair size increase');
    const fd = fs.openSync(destination, 'wx');
    try {
      for (const part of result.parts) {
        let offset = 0;
        while (offset < part.length) offset += fs.writeSync(fd, part, offset, part.length - offset);
      }
      fs.fsyncSync(fd);
    } finally { fs.closeSync(fd); }
    const corrected = fs.readFileSync(destination);
    response.verification = verify(original, corrected, report);
    response.playback_sha256 = crypto.createHash('sha256').update(corrected).digest('hex');
  }
  console.log(JSON.stringify(response));
}
if (require.main === module) {
  try { main(); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = {verify, sameNetwork, frames};
