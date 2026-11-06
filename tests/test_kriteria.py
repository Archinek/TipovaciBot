"""Kontrola konzistence kritérií a konfigurace (bez sítě)."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bot import config, kriteria  # noqa: E402


def test_kriteria_konzistence():
    cfg = config.nacti_cfg()
    sporty = set(cfg["sporty"])
    soubory = {p.stem for p in (ROOT / "kriteria").glob("*.yaml")}
    assert sporty <= soubory, f"sport v sporty.yaml bez souboru kriterií: {sporty - soubory}"
    celkem = 0
    for s in sorted(soubory):
        d = yaml.safe_load(open(ROOT / "kriteria" / f"{s}.yaml", encoding="utf-8"))
        assert d["sport"] == s, s
        ks = d["kriteria"]
        if len(ks) < 10:
            print(f"   ⚠️ {s}: jen {len(ks)} kritérií (původně 15-30)")
        ids = [k["id"] for k in ks]
        assert len(ids) == len(set(ids)), f"{s}: duplicitní id"
        for k in ks:
            assert k["w"] in (1, 2, 3) and k["typ"] in ("veto", "kontext"), (s, k)
            assert k["id"].isascii() and k["co"].strip(), (s, k["id"])
        assert any(k["typ"] == "veto" and k["w"] == 3 for k in ks), f"{s}: žádné veto s váhou 3"
        celkem += len(ks)
    print(f"   {len(sporty)} sportů, {celkem} kritérií")


def test_prompt_vyber():
    nast = config.nacti_cfg()["nastaveni"]
    veto, kont = kriteria.pro_prompt("fotbal", nast)
    assert len(veto) <= nast.get("veto_max_kriterii", 12) and len(kont) <= nast.get("kontext_max_kriterii", 6)
    assert veto and all(":" in x for x in veto + kont)
    assert kriteria.pro_prompt("neexistuje", nast) == ([], [])


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("✅", n)
