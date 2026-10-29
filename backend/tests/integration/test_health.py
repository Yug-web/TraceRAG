from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_contract_without_external_services():
    settings = Settings(_env_file=None, environment="test")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_describes_health_endpoint():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        specification = client.get("/openapi.json").json()
    assert "200" in specification["paths"]["/api/health"]["get"]["responses"]
