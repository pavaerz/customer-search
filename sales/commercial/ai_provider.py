"""Opt-in JSON providers in an interruptible, owned process. No auto installation."""
import http.client
import ipaddress
import json
import multiprocessing
import os
import socket
import ssl
import time
from urllib.parse import urlsplit
from .ai_schema import SYSTEM,response_schema,unknown_output


class ProviderError(ValueError):
    """Sanitized transport code; never carries response prose or credentials."""
    def __init__(self,code,usage=None,retryable=False):
        super().__init__(code)
        self.usage=usage or {}
        self.retryable=retryable


def _remote_usage(data):
    raw=data.get('usage') or {}
    if not isinstance(raw,dict):return {}
    usage={}
    for source,target in [('prompt_tokens','input_tokens'),('completion_tokens','output_tokens'),('total_tokens','total_tokens')]:
        value=raw.get(source)
        if type(value) is int and 0<=value<=10_000_000:usage[target]=value
    for field,source,target in [('prompt_tokens_details','cached_tokens','cached_input_tokens'),('completion_tokens_details','reasoning_tokens','reasoning_tokens')]:
        details=raw.get(field) or {}
        value=details.get(source) if isinstance(details,dict) else None
        if type(value) is int and 0<=value<=10_000_000:usage[target]=value
    return usage


def _remote_response(data):
    if not isinstance(data,dict):raise ProviderError('provider_response_invalid')
    usage=_remote_usage(data)
    choices=data.get('choices')
    if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
        raise ProviderError('provider_response_invalid',usage)
    choice=choices[0];message=choice.get('message')
    if not isinstance(message,dict):raise ProviderError('provider_response_invalid',usage)
    if message.get('refusal'):raise ProviderError('provider_response_refusal',usage)
    reason=choice.get('finish_reason')
    if reason=='length':raise ProviderError('provider_response_truncated',usage)
    if reason=='content_filter':raise ProviderError('provider_response_filtered',usage)
    if reason!='stop' or message.get('tool_calls') or message.get('function_call'):
        raise ProviderError('provider_response_unexpected_finish',usage)
    output=message.get('content')
    if not isinstance(output,str) or not output.strip():raise ProviderError('provider_response_empty',usage)
    return {'output':output,'usage':usage}


def endpoint_valid(value,provider):
    u=urlsplit(value)
    if u.username or u.password or u.query or u.fragment or not u.hostname:raise ValueError('AI endpoint must not contain credentials, query or fragment')
    try:port=u.port
    except ValueError:raise ValueError('Invalid AI endpoint port') from None
    if provider=='LOCAL':
        if u.scheme!='http' or u.hostname not in ('127.0.0.1','::1') or port in (None,0,8765,8888):raise ValueError('LOCAL requires explicit loopback runtime port')
    elif provider=='REMOTE':
        if u.scheme!='https' or u.hostname in ('localhost','localhost.localdomain'):raise ValueError('REMOTE requires public HTTPS endpoint')
        try:
            if not ipaddress.ip_address(u.hostname).is_global:raise ValueError('REMOTE endpoint is not public')
        except ValueError as exc:
            if str(exc)=='REMOTE endpoint is not public':raise
    else:raise ValueError('Invalid endpoint provider')
    return value


class _PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses=socket.getaddrinfo(self.host,self.port,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('non_public_remote_address')
        ip=addresses[0][4][0]
        sock=socket.create_connection((ip,self.port),self.timeout)
        self.sock=self._context.wrap_socket(sock,server_hostname=self.host)


def _request(config,payload):
    provider=config['provider'];endpoint=config['endpoint'];endpoint_valid(endpoint,provider)
    from .ai_tasks import request_schema,system_for,REQUEST
    task=payload.get('task',REQUEST);schema=request_schema(payload)
    if task in ('RESEARCH_SCREEN_6','RESEARCH_READ_6','COMMERCIAL_DECISION_1'):
        from sales.agent6.grounding import provider_payload
        payload=provider_payload(payload)
    messages=[{'role':'system','content':system_for(task,payload)},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
    if provider=='LOCAL':
        body={'model':config['model'],'messages':messages,'stream':False,'format':schema,'options':{'num_predict':config['max_output_tokens'],'num_ctx':config['max_input_tokens']+config['max_output_tokens']}}
    else:
        body={'model':config['model'],'messages':messages,'max_completion_tokens':config['max_output_tokens'],'response_format':{'type':'json_schema','json_schema':{'name':'commercial_advisory','strict':True,'schema':schema}}}
        # Explicit model contracts; do not infer capabilities from a prefix.
        # Sol supports medium, not none. Completion cap includes reasoning.
        if urlsplit(endpoint).hostname=='api.openai.com':
            body['store']=False
            if config['model']=='gpt-5.4-mini':body['reasoning_effort']='none'
            elif config['model']=='gpt-6.1-sol':body['reasoning_effort']='medium'
    headers={'Content-Type':'application/json','Accept':'application/json'}
    if provider=='REMOTE':
        key=os.environ.get('CUSTOMERSEARCH_AI_API_KEY')
        if not key or not key.strip():raise ProviderError('remote_api_key_missing')
        headers['Authorization']='Bearer '+key
    u=urlsplit(endpoint);connection=(_PinnedHTTPS if provider=='REMOTE' else http.client.HTTPConnection)(u.hostname,u.port,timeout=config['timeout'])
    try:
        connection.request('POST',u.path or '/',body=json.dumps(body).encode(),headers=headers)
        response=connection.getresponse()
        if response.status!=200:
            # No error body is logged; it may echo prompts or secrets. No retry
            # on auth/schema/account errors. Transient retries remain budgeted.
            raise ProviderError('provider_http_'+str(response.status),retryable=response.status in (408,429,500,502,503,504))
        raw=response.read(1_048_577)
        if len(raw)>1_048_576:raise ProviderError('provider_response_too_large')
        try:data=json.loads(raw)
        except (ValueError,UnicodeError):raise ProviderError('provider_response_invalid_json') from None
        if provider=='LOCAL':
            output=data.get('message',{}).get('content');usage={'input_tokens':data.get('prompt_eval_count'),'output_tokens':data.get('eval_count')}
        else:
            return _remote_response(data)
        return {'output':output,'usage':usage}
    finally:connection.close()


def _worker(pipe,config,payload):
    try:pipe.send({'result':_request(config,payload)})
    except ProviderError as exc:
        pipe.send({'error':str(exc),'provider_error':True,'usage':exc.usage,'retryable':exc.retryable})
    except BaseException as exc:
        # Never serialize arbitrary provider exceptions, headers, response or key.
        code=str(exc) if isinstance(exc,ValueError) and str(exc).startswith(('provider_http_','provider_response_','remote_api_key_','non_public_')) else type(exc).__name__
        pipe.send({'error':code})
    finally:pipe.close()


def infer(payload,config,check):
    if config['provider']=='DISABLED':raise ValueError('provider_disabled')
    if config['provider']=='MOCK' and payload.get('task')=='DISCOVERY_TRIAGE_1':
        check()
        return {'output':{'items':[{'id':i['id'],'action':'UNKNOWN','role':'UNKNOWN','quote':'',
                                   'reason':'Offline mock: no source interpretation'} for i in payload['items']]},'usage':{}}
    if config['provider']=='MOCK' and payload.get('task') in ('RESEARCH_PLAN_6','RESEARCH_READ_6','RESEARCH_SCREEN_6'):
        output={'decision':'stop','reason':'Mock offline: nessuna ricerca reale','queries':[]} if payload['task']=='RESEARCH_PLAN_6' else {'analyses':[]}
        return {'output':output,'usage':{'input_tokens':0,'output_tokens':0},'reported_cost':0,'simulated':True}
    if config['provider']=='MOCK':return {'output':unknown_output(payload),'usage':{'input_tokens':0,'output_tokens':0},'reported_cost':0,'simulated':True}
    context=multiprocessing.get_context('spawn');recv,send=context.Pipe(duplex=False)
    process=context.Process(target=_worker,args=(send,config,payload),daemon=True)
    process.start();send.close();deadline=time.monotonic()+config['timeout']
    try:
        while time.monotonic()<deadline:
            check()
            if recv.poll(.05):
                response=recv.recv()
                if response.get('provider_error'):raise ProviderError(response['error'],response.get('usage'),response.get('retryable',False))
                if 'error' in response:raise RuntimeError(response['error'])
                return response['result']
            if not process.is_alive():raise RuntimeError('provider_worker_exited')
        raise TimeoutError('ai_timeout')
    finally:
        recv.close()
        if process.is_alive():process.terminate()
        process.join(timeout=.5)
        if process.is_alive():process.kill();process.join(timeout=.5)
        if process.is_alive():raise RuntimeError('provider_cleanup_failed')
