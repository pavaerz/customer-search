"""Channel-specific research briefs. Queries remain generated and validated."""
from . import canonical_flow

BRIEFS={
    'AZIENDE':{
        'goal':'Discover real operating companies and complete digital projects. Separate proactive website opportunities from declared buying requests.',
        'strategies':['official_company_sector_region','explicit_complete_project'],
        'required_checks':['official identity','commercial activity','observed website evidence','whole-project scope','commercial fit'],
        'not_demand':['dated appearance','single missing meta tag','catalogue alone','funding alone'],
    },
    'AGENCIES':{
        'goal':'Find digital agencies explicitly inviting external developers, frontend/WordPress freelancers or technical partners, including careers pages.',
        'strategies':['freelance_role','external_technical_partner','project_contract'],
        'required_checks':['agency identity','external invitation','original invitation','currentness'],
        'affinity':'Stack is optional: use matching skills for ranking, not exclusion. A generic external invitation by a digital agency is a partner lead, never an active paid assignment.',
        'not_demand':['agency selling services','employee-only vacancies','travel agencies'],
    },
    'SOCIAL':{
        'goal':'Find public indexed requests by identifiable professional buyers on LinkedIn, Instagram or other permitted social platforms. Search one platform per query.',
        'strategies':['linkedin_public_request','instagram_public_request','other_public_social_request'],
        'required_checks':['author or company','original public post','request date','paid external scope','Italy eligibility'],
        'not_demand':['supplier self-promotion','reposted anonymous request','indexed snippet without readable original','employee-only jobs'],
    },
    'STARTUPS':{
        'goal':'Find named startups seeking development, freelance collaboration or a technical cofounder. Separate paid work, equity-only and unknown arrangements.',
        'strategies':['paid_mvp_supplier','freelance_product_development','launch_website','technical_cofounder'],
        'required_checks':['startup identity','concrete unfinished project','supplier or freelance relationship','security and integrations','maintenance scope'],
        'not_demand':['employee job','already launched app','investment without development requirement'],
    },
    'NEWS':{
        'goal':'Identify the company involved in a dated expansion, product launch or market change, then verify its official digital presence and a specific related gap.',
        'strategies':['market_expansion','new_product_line','brand_launch'],
        'required_checks':['original event','publication and event dates','subject distinct from publisher','official company site','independent relevant digital gap'],
        'not_demand':['generic economic statistics','publisher as buyer','event alone','old news as current project request','simple translation need as full rebuild'],
    },
}


def brief(flow,regions,round_index):
    canonical=canonical_flow(flow)
    result={**BRIEFS[canonical], 'channel':canonical,
        'professional_profile':'Complete websites/rebuilds, WooCommerce, frontend, web apps/MVP; ongoing external collaborations allowed. Exclude isolated maintenance/CSS/content fixes. Unknown scope/budget stays unknown. Stack guides affinity, never agency eligibility.',
        'query_constraints':'One service and one commercial action per query. If a territory is used, use only one. At most two OR alternatives; no lists of all technologies/regions. Each strategy must be falsifiable.'}
    result['search_expression']='Use short queries: one optional exact invitation phrase (e.g. "collabora con noi") plus a broad role. Avoid stacking exact phrases or narrow sector/stack/project terms. On zero results simplify incidental terms or change source; on irrelevant results tighten buyer/request direction. A year alone is not an event. Examples are not fixed queries. Verify eligibility and project scope on originals.'
    if regions:result['eligibility_focus_region']=regions[round_index%len(regions)]
    result['geography_instruction']='Configured regions are eligibility criteria to verify on originals, not mandatory words in every query. For local operating-company discovery include one configured territory. For external collaborations, careers and remote work, a query without a region may recover relevant sources whose titles omit their location. Do not infer Italy eligibility from Italian wording or remote alone.'
    if canonical in ('AZIENDE','NEWS') and regions:
        result['focus_region']=regions[round_index%len(regions)]
    if canonical=='AGENCIES':
        result['source_strategy']='Propose at least one discovery direction for original careers/join pages that invite external technical collaborators. Combine an invitation/page purpose with a technical role and a freelance/PIVA/external relation; do not require the literal word agency, a region, a named stack and a project type all together. Prefer language agencies actually publish over procurement abstractions such as selection of suppliers, unless memory supports that source. A second direction may explore a distinct technical partnership. Never seed specific previously reviewed companies as new discoveries.'
        result['verification_focus']='Read the actual vacancy or standing invitation, not a search snippet. Verify role-specific contract, location, hours, closure and response channel. Archived vacancies and future-CV forms do not prove an open assignment; a distinct standing external invitation can still be useful.'
    if canonical=='STARTUPS':
        result['source_strategy']='Seek founder/product-team requests on originals, careers or public professional posts. Search a concrete technical collaboration or product need, not an invented requirement to rebuild a startup website. The literal startup label and a region are optional search terms: verify the real venture, unfinished scope, contract/equity and Italy eligibility on the source. Generic funding news or companies advertising MVP development are not buyers.'
    if canonical=='NEWS':
        result['query_constraints']='One territory and a concrete company event per query, at most two OR alternatives. No requirement for web/developer words: the digital gap must be checked later on the identified company site.'
    if canonical=='AZIENDE':
        result['query_constraints']+=' For official_company_sector_region use sector + territory + operating activity; no hiring/developer keyword is required. The website audit must establish the opportunity afterwards.'
        result['sector_instruction']='Choose a specific product or operating service (e.g. precision machining, packaging, windows, furniture, food production, hospitality). These are examples, not fixed queries or a whitelist. Generic company/products/ecommerce is insufficient. Generate distinct sectors, source approaches and falsifiable hypotheses; use discovery_adaptation to avoid regional clones of exhausted families.'
    result['adaptation_instruction']='After three actual empty or mostly irrelevant searches in the same family, change sector, source type or commercial action. Merely changing the region is not a new strategy. Keep allowed regions. Do not treat transport errors as negative commercial evidence.'
    if canonical not in ('NEWS',):
        result['request_direction']='For explicit demand, search the requested external technical role or development activity. Generic partner + ecommerce/WordPress also retrieves franchisees and sales partners; specify technical partnership or developers. Richiesta preventivo alone finds suppliers quote forms, not buyers. Keep proactive company discovery separate. Do not assume a digital business is requesting digital development.'
    if canonical=='SOCIAL':
        result['focus_platform']='linkedin.com' if flow=='LINKEDIN' else ('linkedin.com','instagram.com','bsky.app','mastodon.social')[round_index%4]
        result['query_constraints']+=' Include site:'+result['focus_platform']+'. Do not automate login or bypass access restrictions.'
    return result


def recovery_proposals(flow,regions,receipts):
    """A few falsifiable alternatives after observed failure, never fake AI plans.

    They pass the same policy, history, balance and saturation gates as AI
    proposals. No widening geography or treating hypotheses as requests.
    """
    from .query_pipeline import strategy_balance
    balance=strategy_balance(flow,receipts)
    recent=[r for r in receipts if isinstance(r.get('results'),int) and not r.get('technical_error')][:3]
    if not balance['required'] and not (len(recent)>=3 and sum(r['results']==0 for r in recent)>=2):return []
    region=regions[0] if regions else 'Italia'
    templates={
        'AZIENDE':[('explicit_complete_project','azienda "cerchiamo" "sviluppatore freelance" sito web'),
                   ('official_company_sector_region','produttore componenti meccanici sito ufficiale')],
        'AGENCIES':[('external_technical_partner','agenzia "collabora con noi" frontend'),
                    ('project_contract','agenzia "outsourcing" "cerchiamo" sviluppatori')],
        'SOCIAL':[('linkedin_public_request','site:linkedin.com/posts "cerchiamo" "sviluppatore freelance"'),
                  ('linkedin_public_project','site:linkedin.com/posts "cerco" "fornitore" "sito web"')],
        'STARTUPS':[('paid_mvp_supplier','startup "cerchiamo" "fornitore" MVP'),
                    ('freelance_product_development','startup "collabora con noi" sviluppatore freelance')],
        'NEWS':[('new_product_line','azienda "lancia" "nuova linea prodotti"'),
                ('market_expansion','impresa "nuovo mercato" espansione')],
    }
    return [{'query':text+' '+region,'strategy':strategy,
        'objective':BRIEFS[flow]['goal'],
        'hypothesis':'Una fonte specifica può documentare un soggetto e un bisogno da verificare; nessuna domanda presunta.',
        'missing':'Verify official subject, original evidence and relevant digital gap or external request.',
        'expected_source':'specific original company page or public request',
        'success':'identified subject and attributable relevant commercial evidence',
        'stop_condition':'no attributable evidence, inaccessible original or irrelevant source',
        'origin':{'kind':'deterministic_recovery_after_observed_outcomes'}} for strategy,text in templates.get(canonical_flow(flow),[])]
