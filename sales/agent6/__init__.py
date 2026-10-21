"""Opt-in, evidence-bound commercial research; historical engines remain intact."""
VERSION='9.2.2'
FLOWS={'AZIENDE':'Aziende','AGENCIES':'Agenzie','SOCIAL':'Social','STARTUPS':'Startup','NEWS':'Notizie aziendali'}
def canonical_flow(flow):return 'SOCIAL' if flow=='LINKEDIN' else flow
def flow_label(flow):return FLOWS.get(canonical_flow(flow),flow)
def flow_aliases(flow):return ('SOCIAL','LINKEDIN') if canonical_flow(flow)=='SOCIAL' else (flow,)
STATES=('DISCOVERED','IDENTIFIED','RELEVANT','POTENTIAL','VERIFIED','NEEDS_REVIEW','REJECTED','UNVERIFIABLE')

def config(raw=None):
    raw={} if raw is None else raw
    if not isinstance(raw,dict) or set(raw)-{'exploration_percent','memory_hours','max_verification_depth'}:raise ValueError('Impostazioni agente non valide')
    out={'exploration_percent':25,'memory_hours':24,'max_verification_depth':3,**raw}
    for k,lo,hi in [('exploration_percent',10,80),('memory_hours',1,720),('max_verification_depth',1,6)]:
        if type(out[k]) is not int or not lo<=out[k]<=hi:raise ValueError('Impostazione agente fuori intervallo: '+k)
    return out
