"""Synthetic public-post contracts, not proof of live social access or AI accuracy."""
import json
import unittest
from unittest.mock import patch

import test_ai_first as model_contract
import test_ai_first_social as support
from sales.agent6 import social,evidence
from sales.commercial.inspection import document

POST='https://mastodon.social/@mario/123456'
PROFILE='https://mastodon.social/@mario'
OWNER={'identity_status':'verified','name':'Alfa Srl','website':support.OFFICIAL}


def personal_page(subject='Alfa Srl',author_type='Person'):
    page=support.post_page(POST,request=subject+': '+support.REQUEST,profile=PROFILE)
    page['html']=page['html'].replace('<h1>Alfa Srl</h1>','<h1>Mario Rossi</h1>')
    page['html']=page['html'].replace('"author": {"@type": "Organization", "name": "Alfa Srl"',
                                    '"author": {"@type": "'+author_type+'", "name": "Mario Rossi"')
    return page


def context(page=None):
    page=page or personal_page()
    return social.context({'original':True,'entity_name':'Alfa Srl'},page,document(page))


def official(html):
    return {'url':support.OFFICIAL,'checked_at':model_contract.DATE,'status':200,
            'html':'<title>Alfa Srl</title><h1>Alfa Srl</h1>'+html}


class AuthorSubjectSeparation(unittest.TestCase):
    def test_person_is_preserved_separately_from_company(self):
        ctx=context()
        self.assertEqual(ctx['author_name'],'Mario Rossi')
        self.assertEqual(ctx['author_profile'],PROFILE)
        self.assertEqual(ctx['author_type'],'Person')
        self.assertEqual(ctx['subject_name'],'Alfa Srl')
        self.assertTrue(ctx['subject_named_in_post'])
        result=social.reciprocal(ctx,official('<a href="'+POST+'">Il nostro annuncio</a>'),OWNER)
        self.assertTrue(result['verified'])
        self.assertEqual(result['relationship'],'person_post_referenced_by_company')
        self.assertEqual(result['person_role'],'UNKNOWN')
        self.assertEqual(result['proofs'][0]['reference'],POST)

    def test_person_profile_link_does_not_attribute_all_persons_posts(self):
        for target in (PROFILE,POST+'9','https://mastodon.social/@other/123456'):
            result=social.reciprocal(context(),official('<a href="'+target+'">Team</a>'),OWNER)
            self.assertFalse(result['verified'])

    def test_subject_in_comments_or_metadata_is_not_named_by_author(self):
        page=personal_page(subject='Cerchiamo un collaboratore')
        page['html']+='<aside>Alfa Srl</aside>'
        ctx=context(page)
        self.assertEqual(ctx['author_name'],'Mario Rossi')
        self.assertFalse(ctx['subject_named_in_post'])
        self.assertFalse(social.reciprocal(ctx,official('<a href="'+POST+'">Annuncio</a>'),OWNER)['verified'])
        ctx=context(personal_page(subject='Alfa Srls'))
        self.assertFalse(ctx['subject_named_in_post'])

    def test_other_company_repost_unverified_owner_and_unknown_author_stay_unverified(self):
        ctx=context();page=official('<a href="'+POST+'">Annuncio</a>')
        for changed,owner in (({**ctx,'reposted':True},OWNER),
                              (ctx,{**OWNER,'name':'Beta Srl'}),
                              (ctx,{**OWNER,'identity_status':'unverified'}),
                              (context(personal_page(author_type='Organization')),OWNER),
                              (context(personal_page(author_type='Unknown')),OWNER)):
            self.assertFalse(social.reciprocal(changed,page,owner)['verified'])

    def test_reference_from_comments_clients_hidden_or_templates_is_not_official(self):
        link='<a href="'+POST+'">Annuncio</a>'
        for wrapper in ('<div class="comments">{}</div>','<div class="client-logo">{}</div>',
                        '<div hidden>{}</div>','<template>{}</template>','<div class="testimonials">{}</div>'):
            self.assertFalse(social.reciprocal(context(),official(wrapper.format(link)),OWNER)['verified'])

    def test_unknown_selected_subject_still_preserves_observed_author(self):
        page=personal_page()
        ctx=social.context({'original':True},page,document(page))
        self.assertEqual(ctx['author_name'],'Mario Rossi')
        self.assertIsNone(ctx['subject_name'])
        self.assertFalse(social.reciprocal(ctx,official('<a href="'+POST+'">Annuncio</a>'),OWNER)['verified'])

    def test_ui_distinguishes_author_company_and_unverified_person_role(self):
        import subprocess
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const text=fs.readFileSync('static/worklist.js','utf8');
const start=text.indexOf('function agent8SourceContext('),end=text.indexOf('\ndocument.addEventListener',start);
const esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const ctx={esc,link:(u,t)=>'<a href="'+esc(u)+'">'+esc(t)+'</a>'};
vm.createContext(ctx);vm.runInContext(text.slice(start,end),ctx);
const html=ctx.agent8SourceContext({social_source:{url:'https://instagram.com/p/sample/',
 status:'PUBLIC_POST_READ',platform:'instagram.com',author_name:'Mario <script>',
 subject_name:'Alfa <img>',official_identity_link:{verified:true,relationship:'person_post_referenced_by_company'}}});
assert(html.includes('Mario &lt;script&gt;'));
assert(html.includes('Alfa &lt;img&gt;'));
assert(!html.includes('<script>'));assert(!html.includes('<img>'));
assert(html.includes('questo specifico post'));
assert(html.includes('ruolo professionale'));
assert(html.includes('resta da verificare'));
assert(!html.includes('collegamento aziendale verificato.'));
"""
        subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)


class PersonOriginalCycle(unittest.TestCase):
    def test_read_original_then_owner_keeps_person_company_dates_and_attributed_contact(self):
        base=support.OriginalCycle();base.setUp()
        try:
            owner=official('<p>Partita IVA: 12345678901</p>'
                           '<footer>Sede legale: Via Roma 12, 35100 Padova (PD)</footer>'
                           '<a href="'+POST+'">Il nostro invito ai collaboratori</a>')
            calls=[]
            def model(payload,cfg,check):
                calls.append(payload)
                out=model_contract.response(payload)
                out['subject_role']='REQUESTER'
                if len(calls)==1:
                    out.update(decision='NEEDS_RESEARCH',action={
                        'type':'READ_LINK','query':'','link_id':payload['links'][0]['id'],
                        'question':'Verificare che Alfa Srl confermi questo specifico post.'})
                return {'output':out,'usage':{}}
            base.worker.enqueue('candidate','SOCIAL',{'url':POST},'person-original')
            with patch('sales.agent6.research.CompanyWeb.get',side_effect=lambda url:personal_page() if url==POST else owner),patch(
                    'sales.agent6.research.identity_from',return_value=OWNER),patch(
                    'sales.agent6.ai.infer',side_effect=model):
                base.worker.execute(base.task(),lambda:None)
                base.worker.execute(base.task(),lambda:None)
            self.assertEqual(len(calls),2)
            self.assertFalse(calls[0]['identity']['verified'])
            self.assertTrue(calls[1]['identity']['verified'])
            self.assertEqual(calls[1]['social_source']['author_name'],'Mario Rossi')
            self.assertEqual(calls[1]['social_source']['subject_name'],'Alfa Srl')
            self.assertEqual([d['value'] for d in calls[1]['dates']],['2026-10-19'])
            self.assertNotIn(support.COMMENT,'\n'.join(e['text'] for e in calls[1]['evidence']))
            with base.store.connect() as db:
                body=json.loads(db.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
            self.assertEqual(body['decision'],'INTERESTING')
            self.assertEqual(body['entity_name'],'Alfa Srl')
            self.assertEqual(body['social_source']['author_name'],'Mario Rossi')
            self.assertEqual(body['url'],POST)
            self.assertEqual(body['contacts'][0]['actor'],'Alfa Srl')
            self.assertEqual(body['contacts'][0]['value'],'info@alfa.example')
            self.assertEqual(body['open_paid_project'],'UNKNOWN')
        finally:
            base.tearDown()
