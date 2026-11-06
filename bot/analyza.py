"""Obsáhlá analýza ke každému zápasu s kandidáty (rozhodčí, hřiště, počasí, sestavy, program, forma...).

Dělba práce:
  - ČÍSLA (pravděpodobnost, hrana, průměry týmů a rozhodčích) počítá bot z dat. Gemini je NESMÍ měnit.
  - FAKTA ze světa (kdo píská, rozměr hřiště, počasí, sestavy, zranění, program) dohledá Gemini přes Google Search.
    Co nenajde, má označit "nenalezeno". Nesmí si nic vymýšlet.
  - Rozhodčí je důvod v analýze (kolik karet/faulů se dá čekat), nikdy samostatný tip.
Bez klíče Gemini vznikne jen analýza z dat bota (verdikt NEOVĚŘENO).
"""
import json
from collections import OrderedDict

from . import config, kriteria

VERDIKTY = ("OK", "VETO", "NEJISTE")


def _kriteria_text(sport):
    vse = kriteria.nacti(sport)
    radky = []
    for k in sorted(vse, key=lambda k: -k["w"]):
        trhy = f" [trhy: {', '.join(k['trhy'])}]" if k.get("trhy") else ""
        radky.append(f"  - ({k['typ']}, váha {k['w']}) {k['id']}: {k['co']}{trhy}")
    return "\n".join(radky)


def _skupiny(picks):
    z = OrderedDict()
    for p in picks:
        z.setdefault(p["zapas"], []).append(p)
    return z


def _sport(plist):
    return plist[0].get("sport") or "fotbal"


def _polozka(zapas, plist):
    p0 = plist[0]
    if "kurz_fortuna" in p0:                     # fotbalový kandidát z nabídky Fortuny (model + data z historie)
        return {"id": zapas, "zapas": zapas, "sport": p0.get("sport") or "fotbal", "liga": p0.get("liga"), "start_utc": p0.get("start"),
                "kandidati": [{"trh": p["trh"], "kurz_fortuna": p["kurz_fortuna"], "p_model": p["p_model"],
                               "p_trhu_bez_marze": p["p_trh"], "p_mix": p["p"], "hrana": p["edge"],
                               "sazej_od": p["sazej_od"]} for p in plist],
                ("model_ocekavana_esa" if p0.get("sport") == "tenis" else "model_ocekavane_goly_domaci_hoste"): p0.get("mu"),
                "data_z_historie": p0.get("data") or {}}
    return {"id": zapas, "zapas": zapas, "sport": _sport(plist), "liga": p0.get("liga") or p0.get("sport_key"),
            "start_utc": p0.get("start"),
            "kandidati": [{"trh": f"výsledek: {p.get('vyber')}", "ferova_p_podle_pinnacle": p.get("fair_p"),
                           "sazej_od": p.get("min_kurz"), "kurz_tve_kancelare_orientacne": p.get("moje_kurz"),
                           "hrana": p.get("edge"), "tier": p.get("tier")} for p in plist]}


def _prompt(polozky):
    sporty = sorted({p["sport"] for p in polozky})
    krit = "\n".join(f"{sp.upper()}:\n{_kriteria_text(sp) or '  (bez kritérií)'}" for sp in sporty)
    return (
        "Jsi zkušený sportovní analytik a auditor rizik. Níže jsou zápasy s kandidáty na sázku. Matematiku (pravděpodobnosti, "
        "hranu, průměry týmů a rozhodčích) už spočítal bot a ty ji NESMÍŠ měnit. Tvým úkolem je napsat PROFESIONÁLNÍ, DETAILNÍ "
        "analýzu v češtině, která vysvětlí, proč dává smysl (nebo nedává) vsadit na dané trhy, a dohledat tvrdá fakta "
        "k dnešnímu dni přes Google Search.\n\n"
        "KRITÉRIA PODLE SPORTU (každé kritérium s váhou 2 a 3 MUSÍ mít v poli 'faktory' vlastní položku; "
        "kritéria s váhou 1 použij, když jsou relevantní):\n" + krit + "\n\n"
        "PRAVIDLA:\n"
        "- Pro každé kritérium uveď, co jsi zjistil (konkrétní jména, čísla, data) a stav: nalezeno / odhad / nenalezeno. "
        "Nevymýšlej. Co nenajdeš, napiš 'nenalezeno'.\n"
        "- Kdo zápas řídí (rozhodčí/rozhodčí tým/umpire apod.) a rozměry hřiště/kurtu/kluziště a počasí u venkovních sportů "
        "jsou součást analýzy, ne samostatný tip. Pokud 'data_z_historie' obsahují tabulku 'rozhodci_v_lize', bere statistiku "
        "rozhodčího POUZE z ní (při shodě jména), jinak napiš, že statistika není k dispozici.\n"
        "- Neposuzuj výši kurzu. Posuzuj, jestli fakta podporují nebo oslabují předpoklad kandidáta (např. malé hřiště a přísný "
        "rozhodčí podporují Over u faulů; zraněný brankář oslabuje favorita).\n"
        "- verdikt: VETO jen při potvrzeném tvrdém faktu proti sázce (klíčový hráč chybí, startující brankář/nadhazovač "
        "se změnil, extrémní počasí, odstoupení...), OK když fakta sedí, NEJISTE když chybí klíčové informace.\n"
        "- 'pro' a 'proti': konkrétní věty (max 200 znaků), 3-6 položek každého, pokud existují.\n\n"
        'Odpověz POUZE čistým JSON bez Markdownu:\n'
        '{"vysledky":[{"id":"<id zápasu>","verdikt":"OK|VETO|NEJISTE","duvod":"max 200 znaků",'
        '"souhrn":"4-6 vět: celkový obraz zápasu a proč právě tyto trhy",'
        '"faktory":[{"kriterium":"id kritéria","zjisteni":"konkrétně","stav":"nalezeno|odhad|nenalezeno","dopad":"+|-|0 a jednou větou proč"}],'
        '"pro":["..."],"proti":["..."],"riziko":"hlavní riziko v jedné větě",'
        '"komentare_k_trhum":[{"trh":"přesně text trhu z kandidáta","komentar":"1-2 věty"}]}]}\n\n'
        "ZÁPASY:\n" + json.dumps(polozky, ensure_ascii=False)
    )


def _zaklad(plist):
    """Analýza jen z dat bota (bez Gemini)."""
    p0 = plist[0]
    d = p0.get("data") or {}
    pro = []
    for p in plist:
        if "p_model" in p:
            pro.append(f"{p['trh']}: model {p['p_model'] * 100:.0f} % vs. trh {p['p_trh'] * 100:.0f} %, hrana {p['edge'] * 100:+.1f} %.")
        else:
            pro.append(f"Výsledek {p.get('vyber')}: férová pravděpodobnost podle Pinnacle {float(p.get('fair_p') or 0) * 100:.0f} %, sázej od {p.get('min_kurz')}.")
    liga = d.get("liga_prumer_na_zapas") or {}
    souhrn = ""
    if d.get("domaci") and d.get("hoste"):
        h, a = d["domaci"], d["hoste"]
        souhrn = (f"Domácí v posledních {h['zapasu']} zápasech: góly {h.get('goly_pro')}:{h.get('goly_proti')}, rohy {h.get('rohy_pro')}, "
                  f"fauly {h.get('fauly_pro')}, žluté {h.get('zlute_pro')}. Hosté: góly {a.get('goly_pro')}:{a.get('goly_proti')}, "
                  f"rohy {a.get('rohy_pro')}, fauly {a.get('fauly_pro')}, žluté {a.get('zlute_pro')}. "
                  f"Průměr ligy na zápas: {liga}.")
    return {"verdikt": "NEOVERENO", "duvod": "Gemini kontrola neproběhla, analýza je jen z dat bota.", "souhrn": souhrn,
            "pro": pro, "proti": ["Kontextová fakta (rozhodčí, hřiště, počasí, sestavy, zranění) nebyla ověřena."],
            "riziko": "Nezjištěna sestava a zranění.", "komentare_k_trhum": []}


def rozsir(picks, cfg, vola_gemini=None, max_zapasu=None):
    """Přidá ke každému picku klíč 'analyza'. VETO picky vyřadí. -> (platne, vyrazene)."""
    if not picks:
        return [], []
    skup = _skupiny(picks)
    if max_zapasu:
        skup = OrderedDict(list(skup.items())[:max_zapasu])       # rozbor jen pro prvních N zápasů, ostatní picky zůstanou beze změny
    vysl = {z: _zaklad(pl) for z, pl in skup.items()}
    klic = config.env("GEMINI_API_KEY")
    if klic or vola_gemini:
        polozky = [_polozka(z, pl) for z, pl in skup.items()]
        prompt = _prompt(polozky)
        text = None
        if vola_gemini:
            text = vola_gemini(prompt)
        else:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=klic)
                for model in (config.env("GEMINI_MODEL", "gemini-2.5-pro"), "gemini-2.5-flash"):
                    try:
                        r = client.models.generate_content(
                            model=model, contents=prompt,
                            config=types.GenerateContentConfig(tools=[{"google_search": {}}]))
                        text = r.text or ""
                        break
                    except Exception as e:
                        print(f"⚠️ Analýza přes {model} selhala: {e}")
            except Exception as e:
                print(f"⚠️ Gemini nelze inicializovat: {e}")
        if text:
            try:
                data = json.loads(text[text.find("{"): text.rfind("}") + 1])
                for v in data.get("vysledky", []):
                    if v.get("id") in vysl and v.get("verdikt") in VERDIKTY:
                        vysl[v["id"]] = {**v, "verdikt": v["verdikt"]}
            except (ValueError, TypeError) as e:
                print(f"⚠️ Odpověď analýzy nešla přečíst: {e}")
    platne, vyrazene = [], []
    for p in picks:
        if p["zapas"] not in vysl:
            platne.append(p)
            continue
        p["analyza"] = vysl[p["zapas"]]
        (vyrazene if p["analyza"].get("verdikt") == "VETO" else platne).append(p)
    return platne, vyrazene
