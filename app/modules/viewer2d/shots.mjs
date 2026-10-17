// Direction previews are deliberately separate from recorded impact endpoints.
export function directionEndpoint(shot, length = 350) {
  const angles = shot.angles;
  if (!Array.isArray(angles) || angles.length < 2 || !angles.every(Number.isFinite)) return null;
  const pitch = angles[0] * Math.PI / 180, yaw = angles[1] * Math.PI / 180;
  return [shot.origin[0] + length * Math.cos(pitch) * Math.cos(yaw),
    shot.origin[1] + length * Math.cos(pitch) * Math.sin(yaw),
    shot.origin[2] - length * Math.sin(pitch)];
}

export function prepareShots(shots, events) {
  const firing = new Map(events.filter(e => e.kind === 'fire_bullets')
    .map(e => [`${e.tick}:${e.user_steamid}`, e]));
  return shots.map(shot => {
    const e = firing.get(`${shot.tick}:${shot.shooter}`);
    return {...shot, angles: shot.angles || (e && Number.isFinite(e.angles_x) && Number.isFinite(e.angles_y)
      ? [e.angles_x, e.angles_y] : null)};
  });
}

export function comparisonShot(shots, tickrate) {
  // Reuse exactly the same busy five-second interval when comparing styles.
  return shots.reduce((best, shot) => {
    const count = shots.filter(s => s.tick >= shot.tick && s.tick < shot.tick + tickrate * 4).length;
    return count > best.count ? {shot, count} : best;
  }, {shot: null, count: 0}).shot;
}
