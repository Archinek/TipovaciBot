"""Načítání kritérií pro jednotlivé sporty (kriteria/<sport>.yaml).

Každé kritérium: id, w (váha 1-3), typ (veto|kontext), co (co zjistit), trhy (volitelně).
  veto    = informace, která se může změnit těsně před zápasem a zneplatnit cenu
  kontext = strukturální faktor (rozměry hřiště, rozhodčí, styl...); jde do analýzy, ne do vetování
Váhy jsou odhad (ne naměřený vliv). Měřitelné je jen to, jak si sport vede podle CLV v bety.csv.
"""
import yaml

from . import config

DIR = config.ROOT / "kriteria"


def nacti(sport):
    p = DIR / f"{sport}.yaml"
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("kriteria", [])


def pro_prompt(sport, nast):
    """-> (veto_seznam, kontext_seznam) jako krátké texty seřazené podle váhy."""
    vse = nacti(sport)

    def fmt(k):
        trhy = f" [trhy: {', '.join(k['trhy'])}]" if k.get("trhy") else ""
        return f"{k['id']}: {k['co']}{trhy}"

    def vyber(typ, limit):
        # sorted je stabilní: při stejné váze zůstává pořadí ze souboru
        c = sorted((k for k in vse if k["typ"] == typ), key=lambda k: -k["w"])
        return [fmt(k) for k in c[:limit]]

    return (vyber("veto", nast.get("veto_max_kriterii", 12)),
            vyber("kontext", nast.get("kontext_max_kriterii", 6)))
