"""Gemini jako KONTROLOR RIZIK (veto), ne jako zdroj hrany.

Dostane už vybrané kandidáty a ověří přes Google Search jen sport-specifické kontroly
ze sporty.yaml. Odpověď: OK / VETO / NEJISTE + krátký důvod. Při jakékoli chybě
vrací 'NEOVĚŘENO' (bot nespadne, jen to v reportu uvidíš).
"""
import json

from . import config, kriteria

NEOVERENO = ("NEOVĚŘENO", "Kontrola Gemini neproběhla.", "")


def _prompt(polozky):
    return (
        "Jsi kontrolor rizik před sázkou. Matematický model už našel kurzovou hranu "
        "(porovnáním s Pinnacle). TY NEODHADUJ pravděpodobnost a nehledej další hranu.\n"
        "Pro každý zápas ověř přes Google Search POUZE kontroly v poli 'veto_kontroly' k dnešnímu dni "
        "(pole 'kontext_navic' použij jen pro krátká ověřená fakta do pole kontext, nikdy pro verdikt).\n"
        "Verdikt:\n"
        "- VETO = nalezeno konkrétní zjištění, kvůli kterému je fér kurz zastaralý "
        "(chybí klíčový hráč/brankář/nadhazovač, změna sestavy, odložení, odstoupení).\n"
        "- OK = nic takového nenalezeno.\n"
        "- NEJISTE = nelze ověřit.\n"
        "Nevymýšlej fakta. Piš česky, konkrétní jména a čísla, žádné fráze.\n"
        'Odpověz POUZE čistým JSON bez Markdownu: {"vysledky":[{"id":"...","verdikt":"OK|VETO|NEJISTE",'
        '"duvod":"max 160 znaků","kontext":"max 240 znaků ověřených faktů, nebo prázdné"}]}\n\n'
        "ZÁPASY:\n" + json.dumps(polozky, ensure_ascii=False)
    )


def zkontroluj(kandidati, cfg):
    """-> {id: (verdikt, duvod, kontext)}"""
    vysl = {k["id"]: NEOVERENO for k in kandidati}
    klic = config.env("GEMINI_API_KEY")
    if not klic or not kandidati:
        return vysl
    polozky = []
    for k in kandidati:
        veto_k, kontext_k = kriteria.pro_prompt(k["sport"], cfg["nastaveni"])
        polozky.append({"id": k["id"], "zapas": k["zapas"], "sport": k["sport"],
                        "vyber": k["vyber"], "start_utc": k["start"],
                        "veto_kontroly": veto_k, "kontext_navic": kontext_k})
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=klic)
    except Exception as e:  # chybí balíček / špatný klíč
        print(f"⚠️ Gemini nelze inicializovat: {e}")
        return vysl

    modely = [config.env("GEMINI_MODEL", "gemini-3.1-pro-preview"), "gemini-3-flash"]
    for model in modely:
        try:
            r = client.models.generate_content(
                model=model, contents=_prompt(polozky),
                config=types.GenerateContentConfig(tools=[{"google_search": {}}]))
            t = r.text or ""
            data = json.loads(t[t.find("{"): t.rfind("}") + 1])
            for v in data.get("vysledky", []):
                if v.get("id") in vysl and v.get("verdikt") in ("OK", "VETO", "NEJISTE"):
                    vysl[v["id"]] = (v["verdikt"], str(v.get("duvod", ""))[:200],
                                     str(v.get("kontext", ""))[:300])
            print(f"✅ Veto kontrola dokončena modelem {model}.")
            return vysl
        except Exception as e:
            print(f"⚠️ Veto přes {model} selhalo: {e}")
    return vysl
