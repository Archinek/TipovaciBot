"""Gemini jako KONTROLOR RIZIK (veto 2.0), ne jako zdroj hrany."""
import json
from . import config, kriteria

NEOVERENO = ("NEOVĚŘENO", "Kontrola Gemini neproběhla.", "")

def _prompt(polozky):
    return (
        "Jsi striktní faktický auditor rizik před sportovní sázkou. Matematický model a kopule už nezávisle "
        "spočítaly kurzovou hranu a korelaci na okrajových trzích (střely, fauly, rohy, BetBuildery). "
        "TVŮJ ÚKOL: NEODHADUJ pravděpodobnost, nekomentuj výši kurzu a nezamítej sázku proto, že se ti zdá "
        "riskantní nebo že jde o 'Méně než' či vysoký kurz. "
        "Pro každý zápas ověř přes Google Search POUZE tvrdá fyzická fakta k dnešnímu dni:\n"
        "- Hraje daný hráč, na kterého je vypsaná statistika? Není čerstvě zraněný?\n"
        "- Nastupuje očekávaný brankář/nadhazovač?\n"
        "- Nedošlo k náhlé změně rozhodčího?\n\n"
        "Verdikt:\n"
        "- VETO = Nalezeno potvrzené fyzické zranění klíčového hráče pro danou statistiku, zásadní změna sestavy nebo změna rozhodčího.\n"
        "- OK = Hráč hraje, sestava odpovídá, žádné náhlé fyzické překážky.\n"
        "- NEJISTE = Nelze dohledat informace o sestavě.\n\n"
        "Nevymýšlej fakta. Piš česky, konkrétní jména a čísla, žádné fráze.\n"
        'Odpověz POUZE čistým JSON bez Markdownu: {"vysledky":[{"id":"...","verdikt":"OK|VETO|NEJISTE",'
        '"duvod":"max 160 znaků","kontext":"max 240 znaků ověřených faktů, nebo prázdné"}]}\n\n'
        "ZÁPASY:\n" + json.dumps(polozky, ensure_ascii=False)
    )

def zkontroluj(kandidati, cfg):
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
    except Exception as e:
        print(f"⚠️ Gemini nelze inicializovat: {e}")
        return vysl

    modely = [config.env("GEMINI_MODEL", "gemini-2.5-pro"), "gemini-2.5-flash"]
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
