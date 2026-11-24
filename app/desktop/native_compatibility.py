"""Fail closed on changed game builds, native libraries or video preferences."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from jobs import STATE, read_json, save_json
from extractor.job_lock import exclusive
import native_viewer as native
from native_security import active_cfg

STORE = STATE/'native-playback-compatibility.json'
ADAPTER_VERSION = 1


def signature(runtime, video):
    parts = {'runtime': runtime['fingerprint'], 'capture': native.checksum(native.capture_library()),
             'video': native.checksum(video), 'adapter': ADAPTER_VERSION}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest(), parts


def require_verified(runtime, video, *, store=None):
    key, _ = signature(runtime, video)
    data = read_json(store or STORE, {})
    records = data.get('profiles', {}) if isinstance(data, dict) else {}
    record = records.get(key, {}) if isinstance(records, dict) else {}
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(record, dict) or not record.get('verified'):
        raise ValueError('Private playback needs a compatibility check for this game build, capture component or video profile. No game was started.')


def record_smoke(result, *, store=None):
    required = ('ok', 'private_config_confirmed', 'demo_active_confirmed', 'original_settings_unchanged',
                'owned_process_stopped', 'screen_size_unchanged')
    if not all(result.get(k) is True for k in required) or result.get('frames', 0) < 60:
        raise ValueError('This test did not satisfy every managed-rendering acceptance check.')
    session = Path(result['session']).resolve()
    if not session.is_relative_to((STATE/'native-sessions').resolve()): raise ValueError('Unknown rendering evidence location.')
    metadata = read_json(session/'session.json', {})
    runtime = native.runtime_profile(native.configured_game())
    if metadata.get('runtime_fingerprint') != runtime['fingerprint']:
        raise ValueError('The installed game changed after this rendering check.')
    video = active_cfg(native.configured_game())/'cs2_video.txt'
    # The copied video preferences must still be byte-identical to the original.
    if native.checksum(session/'profile/cfg/cs2_video.txt') != native.checksum(video):
        raise ValueError('The tested video copy differs from the current original preferences.')
    key, parts = signature(runtime, video)
    target = Path(store or STORE)
    with exclusive(target.with_suffix('.lock')):
        try:
            data = json.loads(target.read_text()) if target.exists() else {'version': 1, 'profiles': {}}
            if data.get('version') != 1 or not isinstance(data.get('profiles'), dict): raise ValueError()
        except (ValueError, AttributeError) as exc: raise ValueError('The existing compatibility history was preserved; its format needs review.') from exc
        data['profiles'][key] = {**parts, 'verified': True, 'validated_utc': datetime.now(timezone.utc).isoformat(),
                                'demo_sha256': metadata.get('demo_sha256'), 'captured_size': result.get('captured_size'),
                                'frames': result['frames'], 'evidence': str(session)}
        save_json(target, data)
    return key
