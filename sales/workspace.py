"""Explicit workspace reset: archive previous results, retain commercial exclusions."""
import json
from .db import now,encode,domain

# Reverse dependency order; company identities and exclusions deliberately remain active.
RESULT_TABLES=('commercial_social_reviews','commercial_discovery','commercial_resources','commercial_revisions','commercial_opportunities','commercial_engine_runs','commercial_outcomes','discovery_transitions','discovery_candidates','discovery_frontier','research_reviews','research_signals','research_assessments','research_events',
 'research_tasks','campaigns','research_documents','prospect_evidence','interactions',
 'prospects','evidence','sources','audits','run_items','runs','legacy_records')

def reset_results(store,backup_path):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM campaigns WHERE status IN ('running','waiting','stopping')").fetchone() or c.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
            raise ValueError('Ferma le ricerche prima di pulire i risultati.')
        c.execute('CREATE TABLE IF NOT EXISTS workspace_resets(id INTEGER PRIMARY KEY,created_at TEXT NOT NULL,backup_path TEXT NOT NULL,counts TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS workspace_archive(reset_id INTEGER NOT NULL REFERENCES workspace_resets(id),source_table TEXT NOT NULL,row_number INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(reset_id,source_table,row_number))')
        rid=c.execute('INSERT INTO workspace_resets(created_at,backup_path,counts) VALUES (?,?,?)',(now(),str(backup_path),'{}')).lastrowid
        counts={}
        for table in RESULT_TABLES:
            rows=c.execute('SELECT * FROM '+table).fetchall();counts[table]=len(rows)
            for n,row in enumerate(rows):c.execute('INSERT INTO workspace_archive VALUES (?,?,?,?)',(rid,table,n,encode(dict(row))))
        # Keep previous contact outcomes effective after their cards leave the active workspace.
        c.execute("INSERT OR IGNORE INTO dismissed_companies(domain,created_at) SELECT d.domain,? FROM commercial_opportunities o JOIN research_domains d ON d.entity_id=o.entity_id WHERE o.manual_state='discarded'",(now(),))
        c.execute("""UPDATE companies SET prior_contacted=1 WHERE id IN (
          SELECT company_id FROM prospects WHERE stage IN ('contacted','replied','proposal','won','lost')
          UNION SELECT p.company_id FROM prospects p JOIN interactions i ON i.prospect_id=p.id WHERE i.kind IN ('contacted','replied','proposal','won','lost'))""")
        for row in c.execute("SELECT payload FROM legacy_records WHERE kind='leads'").fetchall():
            old=json.loads(row['payload']);host=domain(old.get('url') or '') or domain('https://'+str(old.get('domain') or ''))
            contacted=bool(old.get('sent_at') or old.get('status') in ('sent','sending','uncertain','gmail_pending'))
            blocked=old.get('outcome')=='do_not_contact'
            if not host or not(contacted or blocked):continue
            c.execute('''INSERT INTO companies(domain,name,website,created_at,prior_contacted,do_not_contact) VALUES (?,?,?,?,?,?)
              ON CONFLICT(domain) DO UPDATE SET prior_contacted=max(prior_contacted,excluded.prior_contacted),do_not_contact=max(do_not_contact,excluded.do_not_contact)''',
              (host,old.get('company_name') or host,'https://'+host+'/',now(),int(contacted),int(blocked)))
        for table in RESULT_TABLES:c.execute('DELETE FROM '+table)
        # Permit new discovery without stale query pages, while retaining explicit suppressions.
        c.execute('DELETE FROM research_query_memory');c.execute('DELETE FROM research_visited');c.execute('DELETE FROM cache')
        c.execute('UPDATE workspace_resets SET counts=? WHERE id=?',(encode(counts),rid))
        if c.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Integrità dei riferimenti non valida; pulizia annullata.')
    return {'reset_id':rid,'archived_rows':counts,'backup':str(backup_path)}
