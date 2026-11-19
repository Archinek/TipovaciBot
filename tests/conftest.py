import pytest


@pytest.fixture(autouse=True)
def _bez_cekani_pri_opakovani(monkeypatch):
    monkeypatch.setenv("TIPOVACI_BEZ_CEKANI", "1")
    """Testy nesmí čekat na opakování požadavků (na síť se stejně nesahá)."""
    from bot import fortuna
    monkeypatch.setattr(fortuna.Klient, "OPAKOVANI", ())
