"""Harmless loopback page for exercising actual URL-model warning integration."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HOST = 'paypal-security-account-update-verify-login.127.0.0.1.nip.io'
PAGE = b'''<!doctype html><html><head><meta charset="utf-8"><title>PhishGuard harmless warning test</title></head><body style="font-family:system-ui;padding:50px;background:#edfdf1;color:#082c18"><h1>PhishGuard harmless local test</h1><p>This is a local test page, not a real phishing website.</p><p>Its deliberately suspicious hostname can trigger the real URL model. No verdict is hardcoded or overridden.</p><p>No forms, passwords, tracking, external assets or payment inputs are present.</p><p>After protection is enabled, wait for the extension's scam-warning overlay.</p></body></html>'''
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get('Host','').split(':')[0]
        if host not in {HOST,'127.0.0.1','localhost'}:
            self.send_error(400);return
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(PAGE)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'")
        self.end_headers();self.wfile.write(PAGE)
    def log_message(self,*args):pass
if __name__=='__main__':
    print('Harmless test page: http://'+HOST+':8766',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8766),Handler).serve_forever()
