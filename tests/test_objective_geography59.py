"""Real C54 originals and diagnostic answers; synthetic boundaries labelled."""
import copy,gzip,json,unittest
from pathlib import Path
from sales.extract import Document
from sales.commercial.inspection import document
from sales.commercial.municipalities import resolve_quotation,registry
from sales.commercial.geography import resolve_location
from sales.agent6 import evidence,decision
from sales.agent6.grounding import segments,resolve
from sales.agent6.schema import quote
from sales.agent6.subject_geography import validate as validate_geo
import test_ai_first as h

ROOT=Path(__file__).parent/'fixtures/ai_first/geography59'
ROWS=json.loads((ROOT.parent/'discovery58/invalid.json').read_text())

def page(key):return json.loads(gzip.decompress((ROOT/(key+'.json.gz')).read_bytes()))

def facts(row):return [{'field':f['field'],**quote(resolve({'segment_id':f['segment_id']},row['evidence']),row['evidence'])} for f in row['response']['facts']]

class Geography(unittest.TestCase):
 def test_official_snapshot_has_provenance_and_all_municipalities(self):
  data=json.loads((Path(__file__).parents[1]/'sales/commercial/istat_municipalities.json').read_text())
  self.assertEqual(len(data['municipalities']),7894);self.assertEqual(data['license'],'CC BY 4.0')
  self.assertTrue(data['source_url'].startswith('https://www.istat.it/'))
  self.assertEqual(len(data['source_sha256']),64)
  for name,region in [('Castel Maggiore','Emilia-Romagna'),('Bassano del Grappa','Veneto'),('Rho','Lombardia'),('Carmagnola','Piemonte')]:
   self.assertEqual(resolve_quotation(name)['region'],region)

 def test_actual_beautimport_answer_can_complete_its_bounded_read_request(self):
  row=next(r for r in ROWS if r['id']==1395)
  pg=page('beautimport');packet=evidence.packet(pg,document(pg))
  # Existing response link ID is checked against links actually in saved HTML.
  self.assertIn(row['response']['action']['link_id'],{l['id'] for l in packet['links']})
  p=h.payload();p.update(evidence=row['evidence'],unit_id=row['evidence'][0]['unit_id'],
      identity={'verified':False},links=packet['links'],subject_scope_version=1,
      allowed_regions=['Veneto','Emilia-Romagna','Toscana'])
  result,_=decision.validate(row['response'],p)
  self.assertEqual(result['decision'],'NEEDS_RESEARCH')
  self.assertEqual(result['action']['type'],'READ_LINK')
  self.assertEqual(result['compensation'],'UNKNOWN')
  self.assertEqual(result['assessment']['existing_solution'],'NOT_CHECKED')

 def test_unknown_wrong_country_streets_and_prose_do_not_become_places(self):
  for text in ('Via Castel Maggiore 12','serviamo Castel Maggiore','Clienti a Castel Maggiore',
               'Castel Maggiore Group','Castel Maggiore, UK','Castel Maggiore, clienti in Francia',
               'Castel Maggiore (MI)','Parma40+','Torino · Bologna','ComuneInventato','Opera per aziende'):
   self.assertIsNone(resolve_quotation(text),text)
  self.assertEqual(resolve_quotation('Castel Maggiore, settembre 2026')['region'],'Emilia-Romagna')
  self.assertEqual(resolve_quotation('Castel Maggiore (BO)')['region'],'Emilia-Romagna')

 def test_ambiguous_municipality_is_not_arbitrarily_assigned(self):
  names,_=registry();ambiguous=next(v for v in names.values() if len(v)>1)
  self.assertIsNone(resolve_quotation(ambiguous[0][1]))

 def test_registry_does_not_scan_arbitrary_article_text(self):
  self.assertIsNone(resolve_location('Castel Maggiore vende cosmetici')['region'])
  self.assertIsNone(resolve_quotation('La nuova linea viene distribuita a Castel Maggiore'))

 def test_selected_location_must_still_match_allowed_region(self):
  row=next(r for r in ROWS if r['id']==1395)
  with self.assertRaisesRegex(ValueError,'subject_region_not_supported'):
   validate_geo(row['response'],facts(row),{'allowed_regions':['Veneto']})
  output=copy.deepcopy(row['response']);output['subject_geography']['region']='Veneto'
  with self.assertRaisesRegex(ValueError,'subject_region_not_supported'):
   validate_geo(output,facts(row),{'allowed_regions':['Veneto','Emilia-Romagna']})

class Layout(unittest.TestCase):
 def test_real_profile_location_is_not_concatenated_with_age(self):
  pg=page('foundersbase');d=document(pg)
  self.assertIn('\nParma\n40+\n',d['text']);self.assertNotIn('Parma40+',d['text'])
  packet=evidence.packet(pg,d)
  # New evidence has genuine literal positions in the newly extracted text.
  proof=evidence.passages(packet,packet['units'][0],30000,source_content=True)
  for e in proof:
   if e.get('origin')=='original_metadata':continue
   self.assertEqual(e['text'],d['text'][e['offset']:e['offset']+len(e['text'])])
  self.assertTrue(any(s['text']=='Parma' for e in proof for s in segments(e)))
  self.assertEqual(resolve_location('Parma')['region'],'Emilia-Romagna')

 def test_plain_inline_spelling_is_preserved_synthetic(self):
  for html in ('<p>Woo<b>Commerce</b></p>','<span>Front</span><span>end</span>',
               '<p>S.<span>r.</span>l.</p>'):
   self.assertNotIn('\n',Document(html).text)
  self.assertEqual(Document('<p>Woo<b>Commerce</b></p>').text,'WooCommerce')

 def test_layout_boundaries_share_source_content_coordinates_synthetic(self):
  from sales.agent6.source_context import observe
  for marker in ('class="flex"','class="inline-flex gap-1"','style="display: grid;"'):
   html='<main><p>Alfa Srl</p><span '+marker+'>Parma</span><span '+marker+'>40+</span></main>'
   d=Document(html);pg={'url':'https://alfa.example','html':html}
   self.assertIn('Parma\n40+',d.text)
   observed=observe(pg,d.text)
   self.assertTrue(any('Parma' in d.text[a:b] for a,b in observed['ranges']))

 def test_short_company_names_are_not_split_synthetic(self):
  self.assertEqual(Document('<span class="flexible">Al</span><b>fa</b>').text,'Alfa')
  self.assertEqual(Document('<span style="display:inline">Al</span><b>fa</b>').text,'Alfa')

class OwnerAddressProof(unittest.TestCase):
 def test_original_owner_address_is_citable_without_new_web_read(self):
  import test_commercial_validation as original
  for key,region in [('A','Emilia-Romagna'),('B','Lombardia')]:
   pg=original.originals()[key][0];doc=document(pg)
   address=evidence.owner_address_document(pg,doc,{'origin':'page'},True)
   self.assertIsNotNone(address)
   self.assertEqual(address['parent_document_id'],doc['id'])
   self.assertEqual(resolve_location(address['text'])['region'],region)

 def test_unverified_subjects_and_job_units_never_inherit_owner_office(self):
  import test_commercial_validation as original
  pg=original.originals()['A'][0];doc=document(pg)
  self.assertIsNone(evidence.owner_address_document(pg,doc,{'origin':'page'},False))
  self.assertIsNone(evidence.owner_address_document(pg,doc,{'origin':'JobPosting'},True))

 def test_editorial_subject_does_not_receive_publisher_address(self):
  from unittest.mock import patch
  pg=page('beautimport')
  with patch('sales.extract.parse_page',return_value={'editorial':True}):
   self.assertIsNone(evidence.owner_address_document(pg,document(pg),{'origin':'page'},True))
