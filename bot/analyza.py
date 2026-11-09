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
        trhy = f" [trhy: {', '.join(str(x) for x in k['trhy'])}]" if k.get("trhy") else ""
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
        "- 'pro' a 'proti': konkrétní věty (max 200 znaků), 3-6 položek každého, pokud existují.\n"
        "- 'text': SOUVISLÝ profesionální rozbor jako jeden plynulý odstavec (bez odrážek a nadpisů), 8-14 vět, jako by ho psal "
        "zkušený analytik pro sázkaře: začni kontextem zápasu a formou, pak zranění/sestavy, rozhodčí, hřiště a počasí (jen co je "
        "relevantní pro dané trhy), program a motivaci, a na konci shrň, proč model a fakta podporují (nebo nepodporují) právě "
        "tyto trhy a co by sázku zhatilo. Používej konkrétní jména a čísla; co nejsi schopen dohledat, výslovně přiznej.\n"
        "- 'duvera_gemini': celé číslo 1-10, jak moc fakta ze světa podporují kandidáta (1 = fakta mluví proti / nic neověřeno, "
        "10 = vše ověřeno a sedí).\n\n"
        'Odpověz POUZE čistým JSON bez Markdownu:\n'
        '{"vysledky":[{"id":"<id zápasu>","verdikt":"OK|VETO|NEJISTE","duvod":"max 200 znaků",'
        '"souhrn":"2-3 věty: celkový obraz zápasu",'
        '"text":"souvislý rozbor 8-14 vět","duvera_gemini":7,'
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
    return {"verdikt": "NEOVERENO", "duvod": "Gemini kontrola neproběhla, analýza je jen z dat bota.", "souhrn": souhrn, "text": souhrn,
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
                for model in config.gemini_modely():
                    try:
                        print(f"🔎 Analýza: {len(polozky)} zápasů, model {model} (limit 300 s)...")
                        r = config.s_limitem(lambda: client.models.generate_content(
                            model=model, contents=prompt,
                            config=types.GenerateContentConfig(tools=[{"google_search": {}}])), 300)
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


def _prompt_univ(polozky):
    sporty = sorted({p["sport"] for p in polozky})
    krit = "\n".join(f"{sp.upper()}:\n{_kriteria_text(sp) or '  (bez kritérií: použij obecný rozum a to, co dohledáš)'}" for sp in sporty)
    return (
        "Jsi zkušený sportovní analytik. Níže jsou sázky z celé nabídky sázkové kanceláře na různé sporty (včetně méně běžných: "
        "šipky, snooker, vodní pólo, esporty, stolní tenis, rugby...). Pravděpodobnost 'p_trhu' je férová pravděpodobnost "
        "trhu bez marže; NESMÍŠ ji měnit ani vymýšlet jinou. Pro KAŽDOU sázku napiš PROFESIONÁLNÍ rozbor v češtině pro sázkaře "
        "(do poznámky na Tipsport) a dohledej k dnešnímu dni přes Google Search fakta o zápase.\n\n"
        "KRITÉRIA PODLE SPORTU (použij, co je relevantní):\n" + krit + "\n\n"
        "PRAVIDLA:\n"
        "- Nevymýšlej. Co nenajdeš (sestavy, forma, zranění, hlavní vzájemné zápasy, situace v tabulce, soupeř a styl hry), "
        "výslovně napiš 'nenalezeno'. Pokud je to málo známý zápas a nic jsi nenašel, řekni to a spoléhej jen na to, co víš jistě.\n"
        "- 'text': SOUVISLÝ rozbor jako jeden plynulý odstavec (bez odrážek a nadpisů), 6-10 vět: kontext zápasu a forma, "
        "klíčové faktory pro daný trh (u počtu gólů/bodů/setů/framů styl hry a tempo, u vítěze síla a motivace, u handicapu "
        "předpokládaný rozdíl), co hraje pro a proti vybranému výsledku a co by sázku zhatilo. Konkrétní jména a čísla.\n"
        "- verdikt: VETO jen při potvrzeném tvrdém faktu proti sázce (klíčový hráč chybí, zápas odložen/zrušen, odstoupení, "
        "zjevně jiný zápas než v nabídce), OK když fakta sedí, NEJISTE když chybí klíčové informace.\n"
        "- 'duvera_gemini': celé číslo 1-10, jak moc ověřená fakta podporují výběr (1 = fakta proti / nic neověřeno, 10 = vše sedí).\n"
        "- 'pro' a 'proti': 2-4 konkrétní věty (max 160 znaků).\n\n"
        'Odpověz POUZE čistým JSON bez Markdownu:\n'
        '{"vysledky":[{"id":"<id>","verdikt":"OK|VETO|NEJISTE","duvod":"max 160 znaků","text":"rozbor 6-10 vět",'
        '"duvera_gemini":6,"pro":["..."],"proti":["..."],"riziko":"hlavní riziko v jedné větě"}]}\n\n'
        "SÁZKY:\n" + json.dumps(polozky, ensure_ascii=False)
    )


def _zaklad_univ(c):
    return {"verdikt": "NEOVERENO", "duvod": "Gemini kontrola neproběhla, k dispozici je jen tržní pravděpodobnost.",
            "text": f"Výběr {c['vyber']} ({c['trh']}) má podle férové pravděpodobnosti trhu (bez marže) {c['p'] * 100:.0f} %. "
                    "Kontextová fakta (forma, sestavy, zranění, program) nebyla ověřena.",
            "pro": [f"Tržní pravděpodobnost {c['p'] * 100:.0f} % při kurzu {c['kurz']}."], "proti": ["Fakta o zápase nebyla ověřena."],
            "riziko": "Nezjištěná sestava a zranění."}


def rozsir_univ(univ, cfg, vola_gemini=None, davka=6, vlaken=3):
    """Ke každé sázce z výběru celé nabídky přidá 'analyza' (Gemini, dávkově a paralelně), 'sazej_od' a 'duvera'.
    VETO sázky vyřadí. -> (platne, vyrazene). Bez klíče Gemini zůstane jen základní text."""
    import math
    from concurrent.futures import ThreadPoolExecutor
    from . import tipsteri
    if not univ:
        return [], []
    me = float(((cfg.get("fortuna") or {}).get("univerzalni") or {}).get("min_edge", 0.02))
    for c in univ:
        c["sazej_od"] = math.ceil((1 + me) / c["p"] * 100) / 100
    vysl = {c["zapas"]: _zaklad_univ(c) for c in univ}
    klic = config.env("GEMINI_API_KEY")
    if klic or vola_gemini:
        polozky = [{"id": c["zapas"], "zapas": c["zapas"], "sport": c.get("sport"), "liga": c.get("liga"), "start_utc": c.get("start"),
                    "trh": c["trh"], "vyber": c["vyber"], "kurz": c["kurz"], "p_trhu": c["p"]} for c in univ]
        davky = [polozky[i:i + davka] for i in range(0, len(polozky), davka)]

        def _jedna(d):
            prompt = _prompt_univ(d)
            if vola_gemini:
                return vola_gemini(prompt)
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=klic)
            for model in config.gemini_modely():
                try:
                    r = config.s_limitem(lambda: client.models.generate_content(
                        model=model, contents=prompt, config=types.GenerateContentConfig(tools=[{"google_search": {}}])), 300)
                    return r.text or ""
                except Exception as e:
                    print(f"⚠️ Rozbor výběru přes {model} selhal: {type(e).__name__}: {e}")
            return None

        print(f"🔎 Rozbor výběru z celé nabídky: {len(polozky)} sázek v {len(davky)} dávkách (paralelně {vlaken}).")
        with ThreadPoolExecutor(max_workers=vlaken) as ex:
            texty = list(ex.map(lambda d: _bezpecne(_jedna, d), davky))
        for text in texty:
            if not text:
                continue
            try:
                data = json.loads(text[text.find("{"): text.rfind("}") + 1])
                for v in data.get("vysledky", []):
                    if v.get("id") in vysl and v.get("verdikt") in VERDIKTY:
                        vysl[v["id"]] = {**v, "verdikt": v["verdikt"]}
            except (ValueError, TypeError) as e:
                print(f"⚠️ Odpověď rozboru výběru nešla přečíst: {e}")
    platne, vyrazene = [], []
    for c in univ:
        c["analyza"] = vysl[c["zapas"]]
        c["duvera"] = tipsteri.duvera_10_univ(c, c["analyza"])
        (vyrazene if c["analyza"].get("verdikt") == "VETO" else platne).append(c)
    return platne, vyrazene


def _bezpecne(fn, x):
    try:
        return fn(x)
    except Exception as e:
        print(f"⚠️ Dávka rozboru selhala: {type(e).__name__}: {e}")
        return None
