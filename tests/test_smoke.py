from policy_agent.hello import build_chain


def test_chain_builds(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert build_chain() is not None
