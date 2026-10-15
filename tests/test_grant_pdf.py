import tempfile,unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock,patch
from pypdf import PdfWriter
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
from sales.grant_documents import GrantWeb
from sales.providers import PublicWeb
from sales.research_analysis import ResearchWeb,document
from sales.db import Store

class GrantPdfTests(unittest.TestCase):
 def pdf(self,text=True):
  writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
  if text:
   font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
   page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
   content=DecodedStreamObject();content.set_data(b'BT /F1 12 Tf 40 700 Td (Bando di prova. Beneficiari: ditte individuali in Veneto.) Tj ET');page[NameObject('/Contents')]=writer._add_object(content)
  data=BytesIO();writer.write(data);return data.getvalue()
 def read(self,web_type=GrantWeb,raw=None,ip='93.184.216.34',content_type='application/pdf'):
  with tempfile.TemporaryDirectory() as t:
   store=Store(Path(t)/'test.db');store.init();web=web_type(store)
   response=MagicMock();response.status=200;response.read.return_value=raw or self.pdf();response.getheader.return_value=content_type
   conn=MagicMock();conn.getresponse.return_value=response
   with patch.object(web,'policy'),patch('sales.providers.socket.getaddrinfo',return_value=[(0,0,0,'',(ip,80))]),patch('sales.providers.socket.create_connection'),patch('sales.providers.http.client.HTTPConnection',return_value=conn):
    return web._raw('http://www.invitalia.it/test.pdf')
 def test_pdf_text_extracted(self):self.assertIn('ditte individuali',self.read()['plain_text'])
 def test_pdf_not_enabled_for_other_crawlers(self):
  with self.assertRaisesRegex(ValueError,'non testuale'):self.read(PublicWeb)
 def test_scanned_pdf_is_incomplete(self):
  with self.assertRaisesRegex(ValueError,'non leggibile'):self.read(raw=self.pdf(False))
 def test_pdf_preserves_private_ip_protection(self):
  with self.assertRaisesRegex(ValueError,'private'):self.read(ip='127.0.0.1')
 def test_commercial_research_reads_original_pdf_with_provenance(self):
  page=self.read(ResearchWeb);doc=document(page)
  self.assertIn('ditte individuali',doc['text'])
  self.assertEqual(doc['url'],'http://www.invitalia.it/test.pdf')
  self.assertTrue(doc['content_hash']);self.assertIsNone(doc['published_at'])
 def test_commercial_pdf_keeps_scanned_and_private_failures(self):
  with self.assertRaisesRegex(ValueError,'non leggibile'):self.read(ResearchWeb,raw=self.pdf(False))
  with self.assertRaisesRegex(ValueError,'private'):self.read(ResearchWeb,ip='127.0.0.1')
 def test_commercial_html_size_limit_unchanged(self):
  with self.assertRaisesRegex(ValueError,'1,5 MB'):self.read(ResearchWeb,raw=b'x'*1500001,content_type='text/html')
