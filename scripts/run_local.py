#!/usr/bin/env python3
"""Start the loopback dashboard/API without modifying existing environments or data."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not args.check_only:
        import socket
        probe = socket.socket()
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', args.port))
        except OSError:
            from urllib.request import urlopen
            try:
                with urlopen(f'http://127.0.0.1:{args.port}/health', timeout=2) as response:
                    health = json.load(response)
                if health.get('browser_bridge_enabled') and health.get('model_version'):
                    print(f'PhishGuard is already running: http://127.0.0.1:{args.port}')
                    print('Open this address in Google Chrome. A second server is not needed.')
                    return
            except Exception:
                pass
            raise SystemExit(f'Port {args.port} is already in use. Stop the old PhishGuard server with Ctrl+C in its terminal, then run bash start_local.sh from this new main folder again. Your data was not changed.')
        finally:
            probe.close()
    installed = ROOT / 'config/local-install.json' 
    config = json.loads(installed.read_text()) if installed.exists() else {}
    model = ROOT / config.get('url_model', 'models/trained/url-model.json')
    vision = ROOT / config.get('vision_model', 'models/trained/vision-model.pt')
    reports = ROOT / config.get('reports', 'reports')
    if not model.is_file():
        raise SystemExit('URL model missing. Use the complete ZIP including models.')
    os.environ['PHISHGUARD_REPORT_ROOT'] = str(reports)
    from phishguard.common.config import Settings
    from phishguard.api.main import create_app
    settings = Settings(api_key=secrets.token_urlsafe(48), model_path=model,
                        db_path=ROOT/'data/predictions.db', store_events=False,
                        vision_path=vision if vision.is_file() else None,
                        max_request_bytes=8_000_000, allowed_hosts=('127.0.0.1','localhost','::1'))
    app = create_app(settings)
    if args.check_only:
        from fastapi.testclient import TestClient
        with TestClient(app, base_url='http://127.0.0.1') as client:
            response = client.get('/health')
            response.raise_for_status()
            print(json.dumps(response.json(), indent=2))
            for path in ['/', '/live-detection', '/model-and-system', '/assets/app.js']:
                assert client.get(path).status_code == 200, path
            auth={'X-API-Key':settings.api_key}
            prediction=client.post('/api/v1/predict/url',headers=auth,json={'url':'https://example.com'})
            prediction.raise_for_status()
            print('URL inference smoke test passed.')
            if settings.vision_path:
                import base64, io
                from PIL import Image
                image=io.BytesIO();Image.new('RGB',(224,224),'white').save(image,format='PNG')
                prediction=client.post('/api/v1/predict/image',headers=auth,json={'consent':True,'image_base64':base64.b64encode(image.getvalue()).decode()})
                prediction.raise_for_status()
                print('CNN inference smoke test passed on a synthetic image; this is not an accuracy evaluation.')
            print('All three dashboard pages and both configured model loaders checked.')
        return
    import uvicorn
    print(f'Open in Google Chrome — PhishGuard dashboard: http://127.0.0.1:{args.port}')
    print('Keep this terminal open. Ctrl+C stops the local engine. No browsing state is saved.')
    print('Chrome extension: load the extension folder, then click Connect extension in the dashboard.')
    if args.port != 8000:
        print('The packaged extension is configured for port 8000; use that port for browser pairing.')
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
