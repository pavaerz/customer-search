"""Public-IP-pinned browser egress. Chromium never connects directly to page hosts."""
import ipaddress
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from .providers import blocked

def public_addresses(host,port):
    if not host or port not in (80,443):raise ValueError('Destinazione non consentita')
    if blocked('https://'+host):raise ValueError('Fonte esclusa')
    addresses=list(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('Rete privata non consentita')
    return addresses

class SafeProxy:
    def __init__(self):self.sockets=set();self.lock=threading.Lock();self.closed=threading.Event()
    def __enter__(self):
        parent=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def denied(self):
                self.send_response(403);self.send_header('Content-Length','0');self.send_header('Connection','close');self.end_headers();self.close_connection=True
            def do_CONNECT(self):
                upstream=None
                try:
                    parsed=urlsplit('https://'+self.path);host=parsed.hostname;port=parsed.port or 443
                    if parsed.username or parsed.password or parsed.path:raise ValueError('Tunnel non valido')
                    ips=public_addresses(host,port);upstream=socket.create_connection((ips[0],port),timeout=10)
                    with parent.lock:parent.sockets.add(upstream)
                    self.send_response(200,'Connection established');self.end_headers()
                    self.connection.setblocking(False);upstream.setblocking(False)
                    while not parent.closed.is_set():
                        readable,_,_=select.select([self.connection,upstream],[],[],.2)
                        for source in readable:
                            data=source.recv(65536)
                            if not data:return
                            target=upstream if source is self.connection else self.connection
                            target.setblocking(True);target.settimeout(5);target.sendall(data);target.setblocking(False)
                except (OSError,ValueError):
                    if upstream is None:self.denied()
                finally:
                    self.close_connection=True
                    if upstream:
                        with parent.lock:parent.sockets.discard(upstream)
                        upstream.close()
            def do_GET(self):
                upstream=None
                try:
                    p=urlsplit(self.path)
                    if p.scheme!='http' or p.username or p.password:raise ValueError()
                    ips=public_addresses(p.hostname,p.port or 80);upstream=socket.create_connection((ips[0],p.port or 80),timeout=10)
                    with parent.lock:parent.sockets.add(upstream)
                    path=(p.path or '/')+('?' +p.query if p.query else '')
                    headers='\r\n'.join(f'{k}: {v}' for k,v in self.headers.items() if k.lower() not in ('proxy-connection','connection','host','content-length','transfer-encoding'))
                    upstream.sendall((f'{self.command} {path} HTTP/1.1\r\nHost: {p.netloc}\r\nConnection: close\r\n'+headers+'\r\n\r\n').encode('latin-1'))
                    while not parent.closed.is_set():
                        data=upstream.recv(65536)
                        if not data:break
                        self.connection.sendall(data)
                except (OSError,ValueError):
                    if upstream is None:self.denied()
                finally:
                    self.close_connection=True
                    if upstream:
                        with parent.lock:parent.sockets.discard(upstream)
                        upstream.close()
            do_HEAD=do_GET
            do_POST=denied
            do_PUT=denied
            do_DELETE=denied
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        return self
    def __exit__(self,*args):
        self.closed.set()
        with self.lock:
            for sock in self.sockets:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=1)
