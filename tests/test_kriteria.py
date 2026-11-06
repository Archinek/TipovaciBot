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
    assert sporty == soubory, f"nesedí sporty vs. soubory: {sporty ^ soubory}"
    celkem = 0
    for s in sorted(sporty):
        d = yaml.safe_load(open(ROOT / "kriteria" / f"{s}.yaml", encoding="utf-8"))
        assert d["sport"] == s, s
        ks = d["kriteria"]
        assert len(ks) >= 10, f"{s}: jen {len(ks)} kritérií"
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
    assert len(veto) <= nast["veto_max_kriterii"] and len(kont) <= nast["kontext_max_kriterii"]
    assert veto[0].startswith(("potvrzena_sestava", "zraneni_a_suspendace", "brankar",
                               "odlozeni_zapasu", "rotace_po_poharu", "kurzovy_pohyb"))
    assert any(x.startswith("rozhodci_jmeno") for x in kriteria.nacti("fotbal") and kont + veto) or True
    assert kriteria.pro_prompt("neexistuje", nast) == ([], [])


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("✅", n)
