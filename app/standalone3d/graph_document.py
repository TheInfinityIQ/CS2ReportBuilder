"""Strict reader for the text KV3 subset emitted by our graph decompiler.

This is preparation-time inspection, not an animation graph interpreter. Unknown
syntax fails closed; treating a partly parsed document as a graph is unsafe.
"""
import json
import re

_TOKEN = re.compile(r'\s+|<!--.*?-->|//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|[{}\[\]=,]|[^\s{}\[\]=,"]+', re.S)


def loads(text):
    tokens = []
    end = 0
    for match in _TOKEN.finditer(text):
        if match.start() != end:
            raise ValueError(f'Unsupported KV3 syntax at {end}')
        end = match.end()
        token = match.group()
        if token.isspace() or token.startswith(('<!--', '//', '/*')):
            continue
        tokens.append(token)
    if end != len(text):
        raise ValueError(f'Unterminated KV3 token at {end}')
    index = 0

    def take(expected=None):
        nonlocal index
        if index >= len(tokens):
            raise ValueError('Incomplete KV3 document')
        token = tokens[index]
        if expected is not None and token != expected:
            raise ValueError(f'Expected {expected}, got {token}')
        index += 1
        return token

    def value(depth=0):
        if depth > 128:
            raise ValueError('KV3 nesting exceeds preparation limit')
        token = take()
        if token == '{':
            result = {}
            while index < len(tokens) and tokens[index] != '}':
                key = take()
                if key.startswith('"'):
                    key = json.loads(key)
                elif not re.fullmatch(r'[A-Za-z_][\w:]*', key):
                    raise ValueError(f'Invalid KV3 key: {key}')
                if key in result:
                    raise ValueError(f'Duplicate KV3 key: {key}')
                take('=')
                result[key] = value(depth + 1)
                if index < len(tokens) and tokens[index] == ',':
                    take(',')
            take('}')
            return result
        if token == '[':
            result = []
            while index < len(tokens) and tokens[index] != ']':
                result.append(value(depth + 1))
                if index < len(tokens) and tokens[index] == ',':
                    take(',')
            take(']')
            return result
        if token.startswith('"'):
            return json.loads(token)
        if token in ('true', 'false', 'null'):
            return {'true': True, 'false': False, 'null': None}[token]
        if re.fullmatch(r'-?\d+', token):
            return int(token)
        if re.fullmatch(r'-?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?', token):
            number = float(token)
            if not (-float('inf') < number < float('inf')):
                raise ValueError('Non-finite KV3 number')
            return number
        raise ValueError(f'Unsupported KV3 value: {token}')

    result = value()
    if index != len(tokens) or not isinstance(result, dict):
        raise ValueError('Expected one complete KV3 object')
    return result


def objects(value):
    """Walk documents without dropping nested state machines or variations."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)
