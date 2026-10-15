"""Conservative procurement checks. Unspecified requirements remain unknown."""
import re
from datetime import datetime,timezone

def procurement_checks(documents):
    found={};today=datetime.now(timezone.utc).date()
    patterns={
      'eligibility':r'(?:sono ammessi|possono partecipare|ammessi alla procedura).{0,160}(?:liberi professionisti|professionisti individuali)',
      'requirements':r'(?:unici requisiti|requisiti richiesti esclusivamente).{0,180}(?:partita iva|iscrizione all.albo)',
      'fees':r'(?:nessun onere|nessun costo|nessun contributo).{0,70}(?:partecipazione|presentazione)',
    }
    for d in documents:
        # A third-party summary cannot certify procurement eligibility.
        if not d.get('official'):continue
        text=d.get('research_text',d['text'])
        for key,pattern in patterns.items():
            m=re.search(pattern,text,re.I)
            if m:found[key]={'status':'verified','quote':m[0],'url':d['url']}
        m=re.search(r'(?:scadenza|termine (?:di |per la )?presentazione).{0,80}?(\d{1,2})[/-](\d{1,2})[/-](20\d{2})',text,re.I)
        if m:
            try:
                date=datetime(int(m[3]),int(m[2]),int(m[1])).date()
                found['deadline']={'status':'verified' if date>=today else 'expired','date':date.isoformat(),'quote':m[0],'url':d['url']}
            except ValueError:pass
    return {key:found.get(key,{'status':'unknown'}) for key in ('deadline','eligibility','requirements','fees')}
