"""Convert a manually acquired official ISTAT workbook; never downloads at runtime."""
import argparse,hashlib,json,re,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

REGIONS={1:'Piemonte',2:'Valle d’Aosta',3:'Lombardia',4:'Trentino-Alto Adige',5:'Veneto',6:'Friuli-Venezia Giulia',7:'Liguria',8:'Emilia-Romagna',9:'Toscana',10:'Umbria',11:'Marche',12:'Lazio',13:'Abruzzo',14:'Molise',15:'Campania',16:'Puglia',17:'Basilicata',18:'Calabria',19:'Sicilia',20:'Sardegna'}
SOURCE='https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.xlsx'

def convert(path):
 ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 with zipfile.ZipFile(path) as z:
  strings=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
  rows=[]
  for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:row',ns):
   values={}
   for c in row:
    v=c.find('m:v',ns)
    if v is None:continue
    values[re.sub(r'\d','',c.attrib['r'])]=strings[int(v.text)] if c.get('t')=='s' else v.text
   rows.append(values)
 assert rows[0]['E']=='Codice Comune formato alfanumerico'
 assert rows[0]['G']=='Denominazione in italiano'
 municipalities=[[r['E'],r['G'],r['O'],REGIONS[int(r['A'])]] for r in rows[1:] if r.get('E')]
 assert 7500<len(municipalities)<8500 and len({r[0] for r in municipalities})==len(municipalities)
 return municipalities

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('workbook',type=Path);p.add_argument('output',type=Path);p.add_argument('--reference-date',required=True);p.add_argument('--retrieved-at',required=True);a=p.parse_args()
 data={'version':'istat-municipalities-'+a.reference_date,'reference_date':a.reference_date,'retrieved_at':a.retrieved_at,'source_url':SOURCE,'source_sha256':hashlib.sha256(a.workbook.read_bytes()).hexdigest(),'attribution':'Istat — Elenco dei comuni italiani; transformed to selected columns and canonical region labels by CustomerSearch. No endorsement implied.','license':'CC BY 4.0','license_url':'https://creativecommons.org/licenses/by/4.0/','license_notice':'https://www.istat.it/note-legali/','columns':['istat_code','municipality','province_code','region'],'municipalities':convert(a.workbook)}
 a.output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n');print('Municipalities:',len(data['municipalities']))
