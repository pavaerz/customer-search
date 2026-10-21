"""Explicit AI preferences for NEW campaigns; no credentials or inference here."""
import json
from sales.db import encode


def read(store):
    from .ai import validate_config
    with store.connect() as c:
        row = c.execute("SELECT value FROM config WHERE key='commercial_ai'").fetchone()
    return validate_config(json.loads(row[0]) if row else {})


def save(store, values):
    from .ai import validate_config
    config = validate_config(values)
    with store.connect() as c:
        c.execute("INSERT INTO config(key,value) VALUES ('commercial_ai',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (encode(config),))
    return config


def campaign_config(store, filters):
    from .ai import validate_config
    commercial = filters.get('commercial', {})
    if not isinstance(commercial, dict) or set(commercial) - {'ai'}:
        raise ValueError('Impostazioni commerciali non valide')
    return {'ai': validate_config(commercial['ai']) if 'ai' in commercial else read(store)}
