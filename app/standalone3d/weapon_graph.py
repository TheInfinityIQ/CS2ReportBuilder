"""Compile a verified Glock graph subset, preserving original selector wiring.

This deliberately does not claim to execute the full Source state machine,
layers, IK or game prediction. Unsupported reachable nodes invalidate the pack.
"""
import hashlib
import math
from pathlib import Path

if __package__:
    from .graph_document import loads, objects
    from .backend import CACHE, CONVERTER, read, save, digest
    from .stock_assets import _run, canonical
else:
    from graph_document import loads, objects
    from backend import CACHE, CONVERTER, read, save, digest
    from stock_assets import _run, canonical

RESOURCE = 'animation/graphs/viewmodel/viewmodel_gun.vnmgraph+glock.vnmgraph_c'
SCHEMA = 1


class UnsupportedGraph(ValueError):
    pass


def direct_states(value):
    if isinstance(value, dict):
        if value.get('_class') == 'CNmGraphDocStateNode':
            yield value
            return
        for child in value.values():
            yield from direct_states(child)
    elif isinstance(value, list):
        for child in value:
            yield from direct_states(child)


class Compiler:
    def __init__(self, document):
        self.document = document
        self.parameters = {n['m_ID']: n for n in objects(document)
                           if 'm_ID' in n and ('VirtualParameterNode' in n.get('_class', '')
                                              or 'ControlParameterNode' in n.get('_class', ''))}
        self.active = set()

    def root(self, graph, kind='Pose'):
        nodes = [n for n in graph.get('m_nodes', []) if n.get('_class') == f'CNmGraphDoc{kind}ResultNode']
        if len(nodes) != 1:
            raise UnsupportedGraph(f'Expected exactly one {kind} result')
        return self.node(graph, nodes[0])

    def node(self, graph, node):
        identifier = node['m_ID']
        if identifier in self.active:
            raise UnsupportedGraph('Cyclic graph input')
        self.active.add(identifier)
        try:
            return self._node(graph, node)
        finally:
            self.active.remove(identifier)

    def inputs(self, graph, node):
        nodes = {n['m_ID']: n for n in graph['m_nodes']}
        links = {}
        for link in graph.get('m_connections', []):
            if link['m_toNodeID'] != node['m_ID']:
                continue
            pin = link['m_inputPinID']
            if pin in links or link['m_fromNodeID'] not in nodes:
                raise UnsupportedGraph('Invalid or duplicate graph connection')
            source = nodes[link['m_fromNodeID']]
            if link['m_outputPinID'] not in {p['m_ID'] for p in source.get('m_outputPins', [])}:
                raise UnsupportedGraph('Unknown output pin')
            links[pin] = source
        pins = node.get('m_inputPins', [])
        if set(links) - {p['m_ID'] for p in pins}:
            raise UnsupportedGraph('Unknown input pin')
        return [(p, self.node(graph, links[p['m_ID']]) if p['m_ID'] in links else None) for p in pins]

    def _node(self, graph, n):
        kind = n['_class'].removeprefix('CNmGraphDoc')
        if kind.endswith('ParameterReferenceNode'):
            parameter = self.parameters.get(n['m_parameterUUID'])
            if not parameter:
                raise UnsupportedGraph('Unresolved parameter reference')
            if 'VirtualParameterNode' in parameter['_class']:
                return self.root(parameter['m_pChildGraph'], n['m_parameterValueType'])
            return {'op': 'param', 'name': parameter['m_name']}
        inputs = self.inputs(graph, n)
        values = [v for _, v in inputs]
        if kind.endswith('ResultNode'):
            if len(values) != 1 or values[0] is None:
                raise UnsupportedGraph('Disconnected result')
            return values[0]
        if kind in ('ClipNode', 'AnimationPoseNode'):
            data = n['m_pDefaultVariationData']
            if n.get('m_overrides') or any(v is not None for v in values):
                raise UnsupportedGraph('Dynamic clip overrides not supported')
            if data.get('m_nStartSyncEventOffset', 0) != 0:
                raise UnsupportedGraph('Clip sync offset not supported')
            speed = data.get('m_flSpeedMultiplier', 1.0)
            if not math.isfinite(speed) or speed <= 0:
                raise UnsupportedGraph('Invalid clip speed')
            if kind == 'AnimationPoseNode' and (n.get('m_useFramesAsInput') or data.get('m_variationTimeValue', -1) != -1):
                raise UnsupportedGraph('Dynamic animation-pose time is not supported')
            return {'op': 'clip', 'resource': data['m_clip'],
                    'speed': speed,
                    'loop': n.get('m_bAllowLooping', False),
                    'fixed': n.get('m_fixedTimeValue') if kind == 'AnimationPoseNode' else None}
        if kind in ('NotNode', 'AndNode', 'OrNode'):
            if not values or any(v is None for v in values):
                raise UnsupportedGraph('Disconnected Boolean operand')
            return {'op': kind[:-4].lower(), 'args': values}
        if kind == 'FloatComparisonNode':
            if not values or values[0] is None or n['m_comparison'] not in ('NearEqual', 'GreaterThanEqual', 'LessThanEqual', 'GreaterThan', 'LessThan'):
                raise UnsupportedGraph('Unsupported comparison')
            return {'op': 'compare', 'a': values[0], 'b': values[1] or {'op': 'const', 'value': n['m_flComparisonValue']},
                    'comparison': n['m_comparison'], 'epsilon': n['m_flEpsilon']}
        if kind == 'IDComparisonNode':
            if not values or values[0] is None or n['m_comparison'] != 'Matches':
                raise UnsupportedGraph('Unsupported ID comparison')
            return {'op': 'in', 'arg': values[0], 'values': n['m_values']}
        if kind in ('SelectorNode', 'ClipSelectorNode'):
            secondary = n['m_pSecondaryGraph']
            conditions = [x for x in secondary['m_nodes'] if x['_class'] == 'CNmGraphDocSelectorConditionNode']
            if len(conditions) != 1:
                raise UnsupportedGraph('Missing selector conditions')
            guards = self.inputs(secondary, conditions[0])
            if [p['m_name'] for p, _ in inputs] != n['m_optionLabels'] or [p['m_name'] for p, _ in guards] != n['m_optionLabels']:
                raise UnsupportedGraph('Selector pin order changed')
            if any(v is None for v in values) or any(v is None for _, v in guards):
                raise UnsupportedGraph('Disconnected selector')
            return {'op': 'select', 'options': [{'when': guard, 'pose': pose, 'label': label}
                    for label, (_, guard), pose in zip(n['m_optionLabels'], guards, values)]}
        if kind == 'Blend1DNode':
            pins = {p['m_ID']: v for p, v in inputs}
            points = n['m_blendSpace']['m_points']
            point_ids = {p['m_pinID'] for p in points}
            controls = [v for p, v in inputs if p['m_ID'] not in point_ids]
            if len(controls) != 1 or controls[0] is None or any(pins.get(p['m_pinID']) is None for p in points):
                raise UnsupportedGraph('Invalid blend space')
            return {'op': 'blend', 'value': controls[0], 'points': [
                {'at': p['m_flValue'], 'pose': pins[p['m_pinID']]} for p in points]}
        raise UnsupportedGraph('Unsupported reachable node: ' + kind)

    def compile(self):
        states = [n for n in objects(self.document) if n.get('_class') == 'CNmGraphDocStateNode']
        programs = {}
        for action, name in [('attack', 'ATK0'), ('reload', 'Reload0'), ('idle', 'Idle'), ('empty', 'EmptyPose')]:
            scope = states
            if action == 'reload':
                parents = [n for n in states if n['m_name'] == 'Reload']
                if len(parents) != 1:
                    raise UnsupportedGraph('Normal magazine reload state is ambiguous')
                scope = list(direct_states(parents[0]['m_pChildGraph']))
            matches = [n for n in scope if n['m_name'] == name]
            if len(matches) != 1:
                raise UnsupportedGraph('Missing action state: ' + name)
            programs[action] = self.root(matches[0]['m_pChildGraph'])
        return {'schema': SCHEMA, 'weapon': 'glock', 'resource': RESOURCE,
                'scope': 'Glock action pose selectors only; not full graph execution', 'programs': programs}


def evaluate(program, parameters):
    """Preparation/test oracle. Runtime uses the same small expression contract."""
    op = program['op']
    if op == 'param':
        if program['name'] not in parameters:
            raise UnsupportedGraph('Missing recorded/reconstructed input: ' + program['name'])
        return parameters[program['name']]
    if op == 'const': return program['value']
    if op == 'clip': return program
    if op == 'not': return not evaluate(program['args'][0], parameters)
    if op == 'and': return all(evaluate(x, parameters) for x in program['args'])
    if op == 'or': return any(evaluate(x, parameters) for x in program['args'])
    if op == 'in': return evaluate(program['arg'], parameters) in program['values']
    if op == 'compare':
        a, b = evaluate(program['a'], parameters), evaluate(program['b'], parameters)
        return {'NearEqual': lambda: abs(a-b) <= program['epsilon'], 'GreaterThanEqual': lambda: a >= b,
                'LessThanEqual': lambda: a <= b, 'GreaterThan': lambda: a > b, 'LessThan': lambda: a < b}[program['comparison']]()
    if op == 'select':
        for option in program['options']:
            if evaluate(option['when'], parameters): return evaluate(option['pose'], parameters)
        raise UnsupportedGraph('No supported selector branch')
    if op == 'blend':
        value = evaluate(program['value'], parameters)
        for point in program['points']:
            if math.isclose(value, point['at'], abs_tol=1e-8): return evaluate(point['pose'], parameters)
        raise UnsupportedGraph('Interpolated blend not implemented in action proof')
    raise UnsupportedGraph('Unknown graph operation: ' + op)


def valid_clip(path):
    """A graph receipt cannot reuse a missing/truncated shared pose binary."""
    try:
        data = read(path, {})
        if not isinstance(data, dict) or not isinstance(data.get('variants'), list) or not data['variants']:
            return False
        for variant in data['variants']:
            frames = variant['frames']; bones = variant['bones']; fps = variant['fps']
            if not isinstance(frames, int) or not 1 <= frames <= 4096 or not 1 <= len(bones) <= 256 or not math.isfinite(fps) or fps <= 0:
                return False
            if Path(variant['data']).stat().st_size != frames * len(bones) * 32:
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def prepare_weapon_graph(game, actors, weapons, progress=lambda *args: None):
    if not any(canonical(w) == 'glock' for w in weapons):
        return actors
    game = Path(game)
    folder = Path(actors['models']['ct']).parents[2]
    identity = [SCHEMA, actors['identity'], digest(Path(__file__)), digest(Path(__file__).with_name('graph_document.py'))]
    key = hashlib.sha256(repr(identity).encode()).hexdigest()[:20]
    target = folder/'graphs'/key
    receipt = target/'manifest.json'
    result = {k: v for k, v in actors.items() if k not in ('weapon_graph_gaps', 'weapon_graphs')}
    cached = read(receipt, {})
    if cached.get('identity') == identity and all(valid_clip(p) for p in cached.get('clips', {}).values()) and cached.get('clips'):
        result['weapon_graphs'] = {'glock': cached}; return result
    target.mkdir(parents=True, exist_ok=True)
    progress('actors', 91, 'Preparing original Glock animation selectors once…')
    document = target/'glock.kv3'
    try:
        _run([CONVERTER, '-i', game/'csgo/pak01_dir.vpk', '-f', RESOURCE, '-d', '-o', document, '--threads', '1'],
             target, 'graph-reader.log', limit=4*1024**2, timeout=45)
        pack = Compiler(loads(document.read_text(encoding='utf-8'))).compile()
        resources = {n['resource'] for n in objects(pack) if n.get('op') == 'clip' and n.get('resource')}
        clips = {}
        for resource in sorted(resources):
            compiled = resource + '_c'
            pose = folder/'poses'/hashlib.sha256(compiled.encode()).hexdigest()[:20]
            path = pose/'clip.json'
            if not valid_clip(path):
                pose.mkdir(parents=True, exist_ok=True)
                _run([CACHE/'tools/dotnet-10/dotnet.exe', CACHE/'tools/resource-bridge/ResourceBridge.dll',
                      game/'csgo/pak01_dir.vpk', compiled, pose, folder/'compiled'],
                     target, 'pose-reader.log', limit=16*1024**2, timeout=45)
            if not valid_clip(path): raise UnsupportedGraph('Missing or truncated authored graph clip: ' + resource)
            clips[resource] = str(path)
        pack.update(identity=identity, clips=clips, graph_sha256=digest(document))
        save(receipt, pack)
        result['weapon_graphs'] = {'glock': pack}
    except (ValueError, OSError) as error:
        # Leave existing poses intact and report reduced compatibility explicitly.
        result['weapon_graph_gaps'] = ['Glock graph subset unavailable: ' + str(error)]
    return result
