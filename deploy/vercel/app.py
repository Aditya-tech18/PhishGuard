from pathlib import Path
from phishguard.api.serverless import create_cloud_app

app = create_cloud_app(Path(__file__).parent)
