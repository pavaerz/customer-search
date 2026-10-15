"""Compact only evidence references on the model wire, never source text.

Hash IDs are useful in storage but expensive for a language model to generate.
Call-local aliases also let unchanged excerpts reuse their extraction when an
unrelated footer changes the containing document's hash. Company, URL, role,
dates, text, task and schema remain part of the cache key.
"""
import json

REFERENCES = {'id', 'document_id', 'unit_id', 'support_ids', 'budget_signal_id',
              'existing_solution_ids', 'event_id', 'condition_id'}


def translate(value, mapping, field=None):
    if isinstance(value, dict):
        return {k: translate(v, mapping, k) for k, v in value.items()}
    if isinstance(value, list):
        return [translate(v, mapping, field) for v in value]
    if field in REFERENCES and isinstance(value, str):
        return mapping.get(value, value)
    return value


def compact(data, schema):
    mapping = {}
    for collection, prefix in (('units', 'u'), ('signals', 's')):
        for item in data.get(collection, []):
            ident = item.get('id')
            if isinstance(ident, str) and ident and ident not in mapping:
                mapping[ident] = prefix + str(len(mapping) + 1)
    ident = data.get('document_id')
    if isinstance(ident, str) and ident and ident not in mapping:
        mapping[ident] = 'd1'

    def remap_schema(node, field=None):
        out = dict(node)
        if field in REFERENCES and 'enum' in node:
            out['enum'] = [mapping.get(v, v) for v in node['enum']]
        if 'properties' in node:
            out['properties'] = {k: remap_schema(v, k) for k, v in node['properties'].items()}
        if 'items' in node:
            out['items'] = remap_schema(node['items'], field)
        return out

    return translate(data, mapping), remap_schema(schema), {v: k for k, v in mapping.items()}


def encoded_size(data, schema):
    return len(json.dumps([data, schema], ensure_ascii=False))


def record(*, cached=False, elapsed=0, wait=0, result=None, before=0, after=0, error=False):
    """Aggregate timings in the existing task measurement, without source text."""
    from .discovery_control import _context
    ctx = _context.get()
    if ctx is None:
        return
    metrics = ctx['details'].setdefault('model', {})
    values = {'cache_hits': int(cached), 'calls': int(not cached),
              'errors': int(error), 'seconds': elapsed, 'wait_seconds': wait,
              'input_chars_before': before, 'input_chars_after': after}
    if result:
        for name in ('prompt_eval_count', 'eval_count'):
            if isinstance(result.get(name), (int, float)):
                values[name] = result[name]
        for name in ('load_duration', 'prompt_eval_duration', 'eval_duration'):
            if isinstance(result.get(name), (int, float)):
                values[name + '_seconds'] = result[name] / 1e9
    for name, value in values.items():
        metrics[name] = round(metrics.get(name, 0) + value, 4)
