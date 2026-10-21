"""Distinguish delivered HTML from access to the requested public content."""
import re
from urllib.parse import urlsplit
from sales.extract import Document
from sales.access_status import AccessIssue


def inspect(page):
    doc=Document(page.get('html',''))
    text=doc.text.strip();title=doc.title.strip()
    short=len(text)<2500
    challenge_title=re.search(r'just a moment|attention required|verify (?:you are|your identity)|security check|verifica richiesta|access denied',title,re.I)
    challenge_body=re.search(r'verify (?:that )?you are (?:a )?human|unusual traffic|traffico insolito|verifica.{0,60}(?:robot|essere umano)|checking your browser|enable javascript and cookies to continue',text,re.I)
    challenge_markup=re.search(r'cf-chl-|/cdn-cgi/challenge-platform/',page.get('html',''),re.I)
    if short and (challenge_body or challenge_title and challenge_markup):
        return {'status':'ACCESS_CHALLENGE','content_read':False,'code':'access_challenge',
                'basis':'access_interstitial_not_original_content'}
    path=urlsplit(page.get('url','')).path
    password=any(i.get('type','').lower()=='password' for i in doc.inputs)
    if short and password and (re.search(r'/accounts/login|/login|/signin|/auth(?:/|$)',path,re.I)
                              or re.search(r'log[ -]?in|sign[ -]?in|accedi|accesso',title,re.I)):
        return {'status':'LOGIN_REQUIRED','content_read':False,'code':'login_required',
                'basis':'authentication_form_instead_of_requested_content'}
    status=page.get('status')
    if status!=200:return {'status':'HTTP_ERROR','content_read':False,'code':'http_'+str(status),'basis':'http_status'}
    return {'status':'PUBLIC_CONTENT','content_read':True,'code':None,'basis':'html_content_no_detected_interstitial'}


def require_content(page):
    outcome=inspect(page)
    if not outcome['content_read']:
        raise AccessIssue(outcome['code'],'Contenuto non consultabile: '+outcome['status']+
            '. La risposta ricevuta non è una pagina aziendale esaminata.',url=page.get('url'))
    return outcome
