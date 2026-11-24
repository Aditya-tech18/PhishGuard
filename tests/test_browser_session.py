import pytest
from fastapi.testclient import TestClient
from phishguard.api.main import create_app
from phishguard.common.config import Settings
from phishguard.api.browser_session import BrowserReport, BrowserSession
from pydantic import ValidationError

KEY='k'*40

def client_for(model_path,tmp_path):
    return TestClient(create_app(Settings(api_key=KEY,model_path=model_path,db_path=tmp_path/'unused.db')),client=('127.0.0.1',40123))

def report(**extra):
    return dict(extension_id='a'*32,agent_id='agent-identifier-12345',enabled=True,tabs=[dict(tab_id=1,origin='https://example.com',state='complete',scan_id='one',verdict='low_risk',probability=.1,latency_ms=12)],**extra)

def test_memory_state_dedup_off():
    state=BrowserSession();value=BrowserReport(**report());state.update(value);state.update(value)
    assert state.snapshot()['metrics']['checked']==1
    state.update(BrowserReport(**{**report(),'enabled':False}))
    assert not state.snapshot()['tabs'] and not state.snapshot()['events']

@pytest.mark.parametrize('origin',['https://x.com/private','https://x.com/?secret=1','https://user:password@x.com','file:///tmp/test'])
def test_origin_rejects_sensitive_input(origin):
    value=report();value['tabs'][0]['origin']=origin
    with pytest.raises(ValidationError):BrowserReport(**value)

def test_routes_auth_bootstrap_websocket(model_path,tmp_path):
    with client_for(model_path,tmp_path) as client:
        assert client.get('/api/v1/browser/session').status_code==401
        assert client.post('/api/v1/browser/ui-session').status_code==403
        headers={'sec-fetch-site':'same-origin','x-phishguard-ui':'1'}
        assert client.post('/api/v1/browser/ui-session',headers={**headers,'origin':'https://evil.test'}).status_code==403
        assert client.post('/api/v1/browser/ui-session',headers=headers).json()['api_key']==KEY
        auth={'X-API-Key':KEY}
        assert client.post('/api/v1/browser/report',headers=auth,json=report()).status_code==200
        with client.websocket_connect('/api/v1/browser/ws',headers={'origin':'http://testserver'}) as socket:
            socket.send_json({'type':'authenticate','api_key':KEY})
            assert socket.receive_json()['metrics']['checked']==1
        assert client.post('/api/v1/browser/feedback',headers=auth,json={'tab_id':999,'kind':'false_positive'}).status_code==404
        assert client.post('/api/v1/browser/disconnect',headers=auth).status_code==200
        assert not client.get('/api/v1/browser/session',headers=auth).json()['extension_connected']
        for path in ['/','/live-detection','/model-and-system','/assets/app.js','/assets/fonts.css']:
            response=client.get(path);assert response.status_code==200
            assert "script-src 'self'" in response.headers['content-security-policy']
        assert client.get('/api/v1/browser/evidence',headers=auth).status_code==200

def test_extension_install_routes(model_path,tmp_path):
    import io,zipfile
    with client_for(model_path,tmp_path) as client:
        assert client.get('/api/v1/browser/install-info').status_code==401
        assert client.get('/api/v1/browser/extension-download').status_code==401
        auth={'X-API-Key':KEY}
        info=client.get('/api/v1/browser/install-info',headers=auth).json()
        assert info['extension_available'] is True
        assert info['requires_manual_chrome_install'] is True
        response=client.get('/api/v1/browser/extension-download',headers=auth)
        assert response.status_code==200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.testzip() is None
            assert {'manifest.json','dashboard-bridge.js','connect.html','background.js'} <= set(archive.namelist())
            assert not any(name.endswith(('.env','.key','.pem')) for name in archive.namelist())
        assert client.get('/assets/extension-install.html').status_code==200
