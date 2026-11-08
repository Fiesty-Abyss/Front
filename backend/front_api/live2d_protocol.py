"""Front-owned, dependency-free preview protocol prototype. It does NOT render Live2D.

No third-party SDK, model file, network listener or graphics context is opened.
Start explicitly with ``python -m front_api.live2d_protocol --null-preview``.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import json
import math
import re
import sys
from typing import Protocol

MAX_LINE = 16 * 1024
MAX_MESSAGES = 4096


class ProtocolError(ValueError):
    pass


def json_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate object fields')
        value[key] = item
    return value


def reject_constant(_):
    raise ProtocolError('non-finite JSON constant')


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def keys(value, allowed, required=()):
    require(isinstance(value, dict) and set(value) <= set(allowed) and set(required) <= set(value), 'invalid object fields')
    return value


def number(value, low, high):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high, 'number outside declared bounds')
    return value


def names(value):
    require(isinstance(value, list) and len(value) <= 128 and all(isinstance(x, str) and 0 < len(x) <= 80 and not any(ord(c) < 32 for c in x) for x in value), 'invalid declared action names')
    require(len(value) == len(set(value)), 'duplicate action names')
    return list(value)


def catalog(value):
    keys(value, ('identity', 'kind', 'parameters', 'motions', 'expressions', 'mouth_parameter'), ('identity', 'kind'))
    require(isinstance(value['identity'], str) and re.fullmatch('[a-f0-9]{64}', value['identity']), 'invalid model identity')
    require(value['kind'] == 'generated-protocol-only', 'null prototype accepts generated catalogs only; no runtime or file loading')
    parameters = value.get('parameters', {})
    require(isinstance(parameters, dict) and len(parameters) <= 128, 'parameter budget exceeded')
    names(list(parameters))
    checked = {}
    for name, bounds in parameters.items():
        keys(bounds, ('min', 'max', 'default'), ('min', 'max', 'default'))
        low = number(bounds['min'], -1000000, 1000000)
        high = number(bounds['max'], low, 1000000)
        checked[name] = {'min': low, 'max': high, 'default': number(bounds['default'], low, high)}
    mouth = value.get('mouth_parameter')
    require(mouth is None or isinstance(mouth, str) and mouth in checked, 'mouth mapping must name a declared parameter')
    return dict(identity=value['identity'], kind=value['kind'], parameters=checked,
                motions=names(value.get('motions', [])), expressions=names(value.get('expressions', [])), mouth_parameter=mouth)


class RendererAdapter(Protocol):
    """Future licensed adapters must validate their runtime catalog before publishing it."""
    def load(self, manifest: dict) -> None: ...
    def update(self, values: dict) -> None: ...
    def action(self, kind: str, name: str) -> None: ...
    def release(self) -> None: ...


class NullRenderer:
    """Lifecycle instrument, deliberately no texture, mesh, static image or GPU."""
    def __init__(self):
        self.loaded = False
        self.loads = self.releases = self.actions = 0

    def load(self, manifest):
        self.loaded = True
        self.loads += 1

    def update(self, values):
        pass

    def action(self, kind, name):
        self.actions += 1

    def release(self):
        if self.loaded:
            self.loaded = False
            self.releases += 1


class PreviewSession:
    def __init__(self, adapter: RendererAdapter | None = None):
        self.adapter = adapter or NullRenderer()
        self.ready = self.closed = False
        self.model = None
        self.generation = 0
        self.state = {}
        self.receipts = OrderedDict()

    def status(self):
        return {'mode': 'null-protocol-test', 'renders': False, 'runtime_verified': False,
                'ready': self.ready, 'closed': self.closed, 'generation': self.generation,
                'model_identity': self.model['identity'] if self.model else None,
                'state': self.state, 'frames': 0, 'graphics_contexts': 0}

    def dispose(self):
        try:
            self.adapter.release()
        finally:
            self.model, self.state = None, {}
            self.closed = True

    def _active(self, payload):
        require(self.model is not None, 'no active generated model')
        require(type(payload.get('generation')) is int and payload['generation'] == self.generation, 'stale model generation')

    def execute(self, op, payload):
        if op == 'hello':
            keys(payload, ())
            require(not self.closed, 'session closed')
            self.ready = True
            return self.status()
        require(self.ready and not self.closed, 'handshake required or session closed')
        if op == 'status':
            keys(payload, ())
        elif op == 'load':
            keys(payload, ('catalog',), ('catalog',))
            model = catalog(payload['catalog'])  # Validate fully before releasing current instance.
            self.adapter.release()
            self.adapter.load(model)
            self.model = model
            self.generation += 1
            self.state = {'visible': True, 'fps': 30, 'scale': 1, 'x': 0, 'y': 0, 'rotation': 0,
                          'opacity': 1, 'transparent': True,
                          'parameters': {k: v['default'] for k, v in model['parameters'].items()}, 'expressions': []}
        elif op == 'update':
            keys(payload, ('generation', 'values'), ('generation', 'values'))
            self._active(payload)
            values = keys(payload['values'], ('visible', 'fps', 'scale', 'x', 'y', 'rotation', 'opacity', 'transparent', 'parameters'))
            for key in ('visible', 'transparent'):
                if key in values:require(type(values[key]) is bool, 'flag must be boolean')
            if 'fps' in values:require(type(values['fps']) is int and values['fps'] in (15, 30, 60), 'unsupported fps cap')
            for key, low, high in (('scale', .1, 10), ('x', -10, 10), ('y', -10, 10), ('rotation', -180, 180), ('opacity', 0, 1)):
                if key in values:number(values[key], low, high)
            if 'parameters' in values:
                params = values['parameters']
                require(isinstance(params, dict) and set(params) <= set(self.model['parameters']), 'undeclared model parameter')
                for key, val in params.items():
                    bounds = self.model['parameters'][key]
                    number(val, bounds['min'], bounds['max'])
                values = dict(values, parameters={**self.state['parameters'], **params})
            self.adapter.update(values)
            self.state = {**self.state, **values}  # Latest values coalesce; never a hidden render loop.
        elif op in ('motion', 'expression'):
            keys(payload, ('generation', 'name'), ('generation', 'name'))
            self._active(payload)
            name = payload['name']
            require(isinstance(name, str) and name in self.model[op+'s'], 'action is not declared by active model')
            self.adapter.action(op, name)
            if op == 'expression':
                selected = set(self.state['expressions'])
                selected.remove(name) if name in selected else selected.add(name)
                self.state = {**self.state, 'expressions': sorted(selected)}
        elif op == 'mouth':
            keys(payload, ('generation', 'amplitude'), ('generation', 'amplitude'))
            self._active(payload)
            amplitude = number(payload['amplitude'], 0, 1)
            name = self.model['mouth_parameter']
            require(name is not None, 'mouth mapping not configured; no assumed ParamMouthOpenY')
            bounds = self.model['parameters'][name]
            params = {**self.state['parameters'], name: bounds['min'] + amplitude*(bounds['max']-bounds['min'])}
            self.adapter.update({'parameters': params})
            self.state = {**self.state, 'parameters': params}
        elif op == 'unload':
            keys(payload, ('generation',), ('generation',))
            self._active(payload)
            self.adapter.release()
            self.model, self.state = None, {}
        elif op == 'shutdown':
            keys(payload, ())
            self.dispose()
        else:
            raise ProtocolError('unsupported operation')
        return self.status()

    def receive(self, raw: bytes):
        request_id = None
        try:
            require(len(raw) <= MAX_LINE, 'message budget exceeded')
            request = json.loads(raw.decode('utf-8'), parse_constant=reject_constant, object_pairs_hook=json_object)
            keys(request, ('version', 'id', 'op', 'payload'), ('version', 'id', 'op', 'payload'))
            require(type(request['version']) is int and request['version'] == 1, 'unsupported protocol version')
            require(isinstance(request['id'], str) and re.fullmatch('[a-f0-9]{32}', request['id']), 'invalid request identity')
            request_id = request['id']
            require(isinstance(request['op'], str), 'invalid operation')
            canonical = json.dumps(request, sort_keys=True, allow_nan=False)
            old = self.receipts.get(request_id)
            if old:
                require(old[0] == canonical, 'request identity reused with different content')
                return json.loads(old[1])
            result = {'version': 1, 'id': request_id, 'ok': True, 'result': self.execute(request['op'], request['payload'])}
            encoded = json.dumps(result, allow_nan=False)
            if len(encoded.encode('utf-8')) + 1 > MAX_LINE:
                self.dispose()
                raise ProtocolError('response budget exceeded; session closed')
            self.receipts[request_id] = (canonical, encoded)
            if len(self.receipts) > 128:self.receipts.popitem(last=False)
            return json.loads(encoded)
        except ProtocolError as exc:
            return {'version': 1, 'id': request_id, 'ok': False, 'error': str(exc)}
        except (ValueError, TypeError, RecursionError, UnicodeError):
            # Deliberately do not echo arbitrary input, file paths or runtime exceptions.
            return {'version': 1, 'id': request_id, 'ok': False, 'error': 'malformed command'}
        except Exception:
            try:
                self.dispose()
            except Exception:
                pass
            return {'version': 1, 'id': request_id, 'ok': False, 'error': 'adapter failure; session closed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--null-preview', required=True, action='store_true')
    parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', errors='strict', newline='\n')
    session = PreviewSession()
    try:
        for _ in range(MAX_MESSAGES):
            line = sys.stdin.buffer.readline(MAX_LINE + 1)
            if not line:break
            response = session.receive(line)
            sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False)+'\n')
            sys.stdout.flush()
            if len(line) > MAX_LINE or session.closed:break
    finally:
        session.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
