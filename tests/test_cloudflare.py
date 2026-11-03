import json
from types import SimpleNamespace
import pytest
from rigdeck.gui import cloudflare


def test_fetch_returns_report_without_transferring_credentials(monkeypatch):
    commands=[]
    def run(argv,**kwargs):
        commands.append(argv)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'sites':[{'site':'example.com','requests':1}]}))
    monkeypatch.setattr(cloudflare.subprocess,'run',run)
    assert cloudflare.fetch(['example.com'])['sites'][0]['requests']==1
    assert commands[0][0]=='ssh'
    assert 'ekkos-gui-run' in commands[0][-1]


def test_connection_failure_never_becomes_zero_traffic(monkeypatch):
    monkeypatch.setattr(cloudflare.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout=''))
    with pytest.raises(RuntimeError,match='unavailable'): cloudflare.fetch(['example.com'])
