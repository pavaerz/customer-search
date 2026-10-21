"""Local text estimate, never a token-count API or a runtime vocabulary download.

The provider adds framing that is not fully public. Include schema, messages and
a safety margin; keep recording actual server usage and enforcing ledger limits.
Unknown model families retain the conservative byte bound.
"""
import base64
import gzip
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def encoding():
    import tiktoken
    folder = Path(__file__).resolve().parents[1] / 'tokenizer_data'
    meta = json.loads((folder / 'o200k_base.json').read_text())
    raw = gzip.decompress((folder / 'o200k_base.tiktoken.gz').read_bytes())
    if hashlib.sha256(raw).hexdigest() != meta['sha256']:
        raise ValueError('tokenizer_integrity')
    ranks = {base64.b64decode(token): int(rank)
             for token, rank in (line.split() for line in raw.splitlines())}
    return tiktoken.Encoding(name=meta['name'], pat_str=meta['pat_str'],
                            mergeable_ranks=ranks, special_tokens=meta['special_tokens'])


def estimate(payload, config):
    from .ai_tasks import system_for, request_schema
    from sales.agent6.grounding import provider_payload
    task = payload['task']
    wire = {'messages': [{'role': 'system', 'content': system_for(task,payload)},
                         {'role': 'user', 'content': json.dumps(provider_payload(payload), ensure_ascii=False)}],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'commercial_advisory', 'strict': True, 'schema': request_schema(payload)}}}
    text = json.dumps(wire, ensure_ascii=False)
    try:
        import tiktoken
        # Pinned tiktoken maps gpt-5 / gpt-5-* but predates the dotted alias.
        # This is a local GPT-5-family estimate, not a server-token guarantee.
        family = ('o200k_base' if config['model']=='gpt-5.4-mini'
                  else tiktoken.encoding_name_for_model(config['model']))
    except KeyError:
        family = None
    if family != 'o200k_base' or config['provider'] == 'LOCAL':
        return {'tokens': len(text.encode()) + 128, 'basis': 'conservative_utf8_bytes',
                'exact': False}
    n = len(encoding().encode(text, disallowed_special=()))
    return {'tokens': math.ceil(n * 1.20) + 256, 'text_tokens': n,
            'basis': 'local_o200k_base_with_20_percent_and_256_framing_margin',
            'exact': False}
