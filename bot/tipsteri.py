"""Vzorec nejúspěšnějších tipérů Tipsportu a výběr "tipu dne".

Z veřejných profilů TOP tipérů (screenshoty z 6. 11. 2026) plyne:
  borunja  (TOP 1, ROI ~15 %)  tenis: počet es v zápase / hráče, vítěz zápasu; kurzy 1.6-2.9, vklad 1-1.5 tis.
  pafi     (TOP 2, ROI ~12 %)  NHL: počet střel v zápase (Over/Under), tenis; kurzy 1.6-2.0
  bouchal1 (TOP 3, ROI ~11 %)  NHL: hráč dá gól / získá bod; kurzy 2.5-7.0, většina tiketů prohraje
  Marty37  (TOP 6, ROI ~9 %)   tenis: počet es hráče většinou UNDER (i "méně než 0.5"), kdo zahraje víc dvojchyb, vítěz; kurzy 1.6-2.4
  JirAdam  (TOP 13, ROI ~6 %)  fotbal: fauly, žluté karty, střely na bránu, kdo víc faulů; kurzy 1.8-2.8
  sarka3004                    fotbal: karty, rohy, fauly v pohárech a ligách
Společné: samé SÓLO sázky (žádné kombinace) na statistické trhy, kurz kolem 2.0, vsazeno ráno/dopoledne a kurz se
během dne sráží (2.41→1.88, 1.85→1.57, 2.50→1.80, 5.00→3.65). Zisk dělá odchycený kurz, ne jistota: výhra ~45-55 %.
Over i Under: borunja hraje esa většinou Over, Marty37 u es hráče spíš Under (slabý podávající). Strana tedy není pravidlo, rozhoduje model.

Bot je nekopíruje (tiket je napsaný až po sražení kurzu). Hledá stejné TYPY příležitostí sám a z mnoha kandidátů
vybírá těch pár nejlepších. Váhy rodin níže jsou odhad podle těchto pěti profilů, ne dokázaná pravda: přepiš je podle
vlastních výsledků (log Fortuny, Brier a CLV).
"""

RODINY = {
    "esa": "Tenis: esa", "esa_hrac": "Tenis: esa",
    "df": "Tenis: dvojchyby", "df_hrac": "Tenis: dvojchyby", "df_kdo": "Tenis: dvojchyby",
    "sot": "Fotbal: střely na bránu", "sot_dom": "Fotbal: střely na bránu", "sot_hos": "Fotbal: střely na bránu",
    "fauly": "Fotbal: fauly", "karty": "Fotbal: karty", "rohy": "Fotbal: rohy",
    "goly": "Fotbal: góly", "goly_dom": "Fotbal: góly", "goly_hos": "Fotbal: góly", "goly_1p": "Fotbal: góly", "btts": "Fotbal: góly",
}

VYCHOZI_VAHY = {"Tenis: esa": 1.15, "Tenis: dvojchyby": 1.10, "Fotbal: střely na bránu": 1.10, "Fotbal: fauly": 1.10, "Fotbal: karty": 1.10,
                "Fotbal: rohy": 1.0, "Fotbal: góly": 0.90}


def rodina(typ):
    return RODINY.get(typ, "Ostatní")


def skore(c, cfg=None):
    """Pořadí kandidátů: hrana × důvěra v model × váha rodiny.
    Důvěra klesá s rozchodem model vs. trh (když se model s trhem hodně neshoduje, je pravděpodobnější, že se mýlí model)."""
    t = ((cfg or {}).get("tipsteri") or {})
    vahy = {**VYCHOZI_VAHY, **(t.get("vahy_rodin") or {})}
    max_roz = float(((cfg or {}).get("fortuna") or {}).get("max_rozchod", 0.12)) or 0.12
    duvera = 1.0 - 0.5 * min(abs(c["p_model"] - c["p_trh"]) / max_roz, 1.0)
    return c["edge"] * duvera * vahy.get(rodina(c.get("typ")), 1.0)


def tip_dne(kandidati, cfg=None, n=None):
    """Vybere max n tipů: nejvyšší skóre, nejvýš 1 linie na zápas a nejvýš `max_na_rodinu` z jedné rodiny
    (ať to není pětkrát totéž). Přidá klíče 'skore', 'rodina', 'tip_dne' (pořadí). Vrací vybrané; ostatním doplní skóre."""
    t = ((cfg or {}).get("tipsteri") or {})
    n = int(n if n is not None else t.get("tipu_dne", 3))
    max_rod = int(t.get("max_na_rodinu", 2))
    for c in kandidati:
        c["skore"] = round(skore(c, cfg), 4)
        c["rodina"] = rodina(c.get("typ"))
        c.pop("tip_dne", None)
    vybrane, zapasy, rodiny = [], set(), {}
    for c in sorted(kandidati, key=lambda x: -x["skore"]):
        if len(vybrane) >= n:
            break
        if c["zapas"] in zapasy or rodiny.get(c["rodina"], 0) >= max_rod or c["skore"] <= 0:
            continue
        vybrane.append(c)
        zapasy.add(c["zapas"])
        rodiny[c["rodina"]] = rodiny.get(c["rodina"], 0) + 1
        c["tip_dne"] = len(vybrane)
    for c in kandidati:
        c["vklad_pct"] = vklad_pct(c, cfg)
    jistejsi(kandidati, cfg, vyloucit=zapasy)
    return vybrane


def vklad_pct(c, cfg=None):
    """Doporučený vklad v % banku: zlomkový Kelly (výchozí 1/4) se stropem. Stabilní růst > velké sázky na hranu."""
    t = ((cfg or {}).get("tipsteri") or {})
    kelly = c["edge"] / max(c.get("kurz_fortuna", 2.0) - 1.0, 1e-9)
    return round(max(0.0, min(float(t.get("max_vklad_pct", 2.0)), float(t.get("kelly_frakce", 0.25)) * kelly * 100.0)), 2)


def jistejsi(kandidati, cfg=None, vyloucit=(), n=None):
    """Druhý žebříček: vyšší pravděpodobnost za nižší kurz (Marty37: kurzy 1.6-1.9, ROI ~9 %, vyšší úspěšnost).
    Podmínky: p >= jistejsi_min_p a hrana >= jistejsi_min_edge. Řadí se podle náskoku pravděpodobnosti před hranicí
    vyplacení (p - 1/kurz) × důvěra v model. Zápasy z `vyloucit` (tip dne) se nepoužijí, ať je z čeho vybírat."""
    t = ((cfg or {}).get("tipsteri") or {})
    n = int(n if n is not None else t.get("jistejsich", 2))
    min_p, min_e = float(t.get("jistejsi_min_p", 0.58)), float(t.get("jistejsi_min_edge", 0.02))
    max_roz = float(((cfg or {}).get("fortuna") or {}).get("max_rozchod", 0.12)) or 0.12
    for c in kandidati:
        c.pop("jistejsi", None)
    kand = []
    for c in kandidati:
        if c.get("p", 0) < min_p or c["edge"] < min_e or c["zapas"] in vyloucit or not c.get("kurz_fortuna"):
            continue
        duvera = 1.0 - 0.5 * min(abs(c["p_model"] - c["p_trh"]) / max_roz, 1.0)
        kand.append(((c["p"] - 1.0 / c["kurz_fortuna"]) * duvera, c))
    vybrane, zapasy = [], set()
    for _, c in sorted(kand, key=lambda x: -x[0]):
        if len(vybrane) >= n:
            break
        if c["zapas"] in zapasy:
            continue
        vybrane.append(c)
        zapasy.add(c["zapas"])
        c["jistejsi"] = len(vybrane)
    return vybrane


def duvera_10(c, cfg=None, an=None):
    """Důvěra 1-10 pro políčko v analýze na Tipsport. Z modelu: klesá s rozchodem model vs. trh (6-10), -1 při p pod 45 %;
    podle kontroly Gemini: OK 0, NEOVĚŘENO -1.5, NEJISTÉ -2, VETO -5; když Gemini dá vlastní 'duvera_gemini' (1-10), zprůměruje se."""
    max_roz = float(((cfg or {}).get("fortuna") or {}).get("max_rozchod", 0.12)) or 0.12
    an = an if an is not None else (c.get("analyza") or {})
    d = 10.0 - 4.0 * min(abs(c["p_model"] - c["p_trh"]) / max_roz, 1.0)
    if c.get("p", 0) < 0.45:
        d -= 1.0
    d += {"OK": 0.0, "NEJISTE": -2.0, "VETO": -5.0}.get(an.get("verdikt"), -1.5)
    dg = an.get("duvera_gemini")
    if isinstance(dg, (int, float)) and 1 <= dg <= 10:
        d = 0.5 * d + 0.5 * float(dg)
    return int(round(min(10.0, max(1.0, d))))
