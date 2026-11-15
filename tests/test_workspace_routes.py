from fastapi.testclient import TestClient

from reaction_alpha.api import create_app
from reaction_alpha.config import ReactionAlphaConfig


def test_workspace_login_is_inline_on_deep_links_and_demo_is_independent(tmp_path, monkeypatch):
    app = create_app(ReactionAlphaConfig(simulated=True, paper_trade_db_path=str(tmp_path/"paper.db")))
    service = app.state.reaction_alpha
    client = TestClient(app)
    monkeypatch.setattr(service, "kotak_login_state", lambda: "totp_required")
    for url in ("/", "/stock/INFY", "/history?setup=3", "/journal/analytics", "/pre-trade-scanner"):
        r = client.get(url)
        assert r.status_code == 200 and 'name="totp"' in r.text
        assert not r.history
    for url in ("/demo", "/demo/stock/INFY", "/demo/journal/analytics"):
        assert "/workspace-assets/workspace.js" in client.get(url).text
    monkeypatch.setattr(service, "kotak_login_state", lambda: "not_required")
    assert "/workspace-assets/workspace.js" in client.get("/stock/INFY").text
