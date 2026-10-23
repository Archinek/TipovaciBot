import os
import json
import time
import datetime
import urllib.request
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

# ==========================================
# 0. NAČTENÍ CITLIVÝCH ÚDAJŮ (Z .ENV NEBO GITHUB SECRETS)
# ==========================================
load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

wa_instance = os.environ.get("WA_INSTANCE_ID")
wa_token = os.environ.get("WA_API_TOKEN")
wa_group_id = os.environ.get("WA_GROUP_ID")
github_pages_url = "https://archinek.github.io/TipovaciBot"

client = genai.Client(api_key=api_key)


# ==========================================
# POMOCNÁ FUNKCE: FLEXIBILNÍ HTML ŠABLONA REPORTU
# ==========================================
def sestav_html_stranku(datum_str, data_json):
    """Vytvoří flexibilní HTML report, který se přizpůsobí počtu sázek (0 až N)."""
    
    radky_hlavni = ""
    hlavni_seznam = data_json.get("hlavni", [])
    if hlavni_seznam:
        for t in hlavni_seznam:
            zapas = t.get("zapas", "Neznámý zápas")
            tip = t.get("tip", "-")
            kurz = t.get("kurz", "-")
            sazej_od = t.get("sazej_od", kurz)
            vklad = t.get("vklad", "1.5/10")
            duvera = t.get("duvera", "-")
            uspesnost = t.get("uspesnost", "-")
            stav = t.get("vysledek", "⏳ Čeká na výsledek")
            barva = "#28a745" if "✅" in stav else ("#dc3545" if "❌" in stav else "#6c757d")
            radky_hlavni += (
                f"<tr>"
                f"<td><span class='tip'>{zapas}:</span> {tip}</td>"
                f"<td class='odds'>{kurz}</td>"
                f"<td style='font-weight:bold; color:#0056b3;'>{sazej_od}+</td>"
                f"<td><strong>{vklad}</strong> ({duvera}/10)</td>"
                f"<td>{uspesnost}</td>"
                f"<td style='font-weight: bold; color: {barva};'>{stav}</td>"
                f"</tr>\n"
            )
    else:
        radky_hlavni = "<tr><td colspan='6' style='text-align: center; padding: 20px; color: #666;'>Dnes nebyla v nabídce nalezena žádná sázka splňující přísná kritéria value a VETO filtr. Trpělivost je součástí strategie.</td></tr>"

    radky_alt = ""
    alt_seznam = data_json.get("alternativni", [])
    if alt_seznam:
        for t in alt_seznam:
            zapas = t.get("zapas", "Neznámý zápas")
            tip = t.get("tip", "-")
            kurz = t.get("kurz", "-")
            sazej_od = t.get("sazej_od", kurz)
            vklad = t.get("vklad", "1.0/10")
            duvera = t.get("duvera", "-")
            uspesnost = t.get("uspesnost", "-")
            stav = t.get("vysledek", "⏳ Čeká na výsledek")
            barva = "#28a745" if "✅" in stav else ("#dc3545" if "❌" in stav else "#6c757d")
            radky_alt += (
                f"<tr>"
                f"<td><span class='tip'>{zapas}:</span> {tip}</td>"
                f"<td class='odds'>{kurz}</td>"
                f"<td style='font-weight:bold; color:#0056b3;'>{sazej_od}+</td>"
                f"<td><strong>{vklad}</strong> ({duvera}/10)</td>"
                f"<td>{uspesnost}</td>"
                f"<td style='font-weight: bold; color: {barva};'>{stav}</td>"
                f"</tr>\n"
            )
    else:
        radky_alt = "<tr><td colspan='6' style='text-align: center; padding: 20px; color: #666;'>Žádné alternativní sázky pro tento den.</td></tr>"

    analyzy_html = ""
    for a in data_json.get("analyzy", []):
        nadpis = a.get("nadpis", "Analýza zápasu")
        text = a.get("text", "")
        analyzy_html += f"<h3>{nadpis}</h3>\n<p>{text}</p>\n"

    if not analyzy_html:
        analyzy_html = "<p>Žádné doplňující analýzy, protože systém dnes nevypsal žádné sázky.</p>"

    box_vyhodnoceni = ""
    if data_json.get("vyhodnoceno", False):
        bilance = data_json.get("bilance_souhrn", "Vyhodnoceno")
        seznam_lekci = data_json.get("nove_lekce", [])
        if seznam_lekci:
            polozky_lekci = "".join([f"<li>{lekce}</li>" for lekce in seznam_lekci])
        else:
            polozky_lekci = "<li>Žádné kritické chyby v tento den.</li>"

        box_vyhodnoceni = f"""
        <div class="eval-box">
            <h3>📊 Zpětné vyhodnocení dne: {bilance}</h3>
            <p><strong>Zapsané lekce z chyb do paměti bota:</strong></p>
            <ul>
                {polozky_lekci}
            </ul>
        </div>
        """

    html_dokument = f"""<!DOCTYPE html>
<html>
<head>
    <title>Ranní Sportovní Report pro Investory ({datum_str})</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; color: #333; }}
        .container {{ max-width: 900px; margin: 0 auto; background-color: #ffffff; padding: 25px; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1); }}
        h1 {{ color: #1a1a1a; font-size: 24px; margin-bottom: 20px; text-align: center; }}
        h2 {{ color: #1a1a1a; font-size: 20px; margin-top: 30px; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
        h3 {{ color: #333; font-size: 18px; margin-top: 25px; margin-bottom: 10px; }}
        p {{ line-height: 1.6; margin-bottom: 15px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; color: #555; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .tip {{ font-weight: bold; color: #007bff; }}
        .odds {{ color: #28a745; font-weight: bold; }}
        .back-link {{ display: inline-block; margin-bottom: 15px; color: #007bff; text-decoration: none; font-weight: bold; }}
        .eval-box {{ background-color: #eef6ff; border-left: 5px solid #007bff; padding: 15px; margin-bottom: 25px; border-radius: 4px; }}
        .eval-box h3 {{ margin-top: 0; color: #0056b3; }}
    </style>
</head>
<body>
    <div class="container">
        <a href="../index.html" class="back-link">⬅ Zpět do hlavního skladu všech HTML reportů</a>
        <h1>Ranní Sportovní Report pro Investory ({datum_str})</h1>
        {box_vyhodnoceni}
        <p>Vážení investoři ze skupiny <strong>TIPOVACI_BOT</strong>,</p>
        <p>přinášíme vám náš ranní report. Matematická hrana pochází z kurzů, přičemž Gemini funguje jako kontextový VETO filtr proti skrytým rizikům (zranění, absence, rotace). Pokud některá sekce zůstala prázdná, trh nenabídl dostatečnou hodnotu a systém disciplinovaně vyčkal.</p>

        <h2>Hlavní Value Tipy (kurz >= 1.80)</h2>
        <table>
            <thead>
                <tr>
                    <th>Příležitost (Zápas a Tip)</th>
                    <th>Kurz Fortuna</th>
                    <th>Sázej od</th>
                    <th>Vklad (Důvěra)</th>
                    <th>Pravděpodobnost</th>
                    <th>Výsledek</th>
                </tr>
            </thead>
            <tbody>
                {radky_hlavni}
            </tbody>
        </table>

        <h2>Alternativní Tipy (kurz 1.40 - 1.79)</h2>
        <table>
            <thead>
                <tr>
                    <th>Příležitost (Zápas a Tip)</th>
                    <th>Kurz Fortuna</th>
                    <th>Sázej od</th>
                    <th>Vklad (Důvěra)</th>
                    <th>Pravděpodobnost</th>
                    <th>Výsledek</th>
                </tr>
            </thead>
            <tbody>
                {radky_alt}
            </tbody>
        </table>

        <h2>Detailní analýzy zápasů a Veto kontroly</h2>
        {analyzy_html}

        <p>S pozdravem,</p>
        <p><strong>Váš Tým Sportovních Analytiků (TIPOVACI_BOT)</strong></p>
    </div>
</body>
</html>"""
    return html_dokument


# ==========================================
# KROK 0: BEZPEČNÉ ZPĚTNÉ VYHODNOCENÍ ARCHIVU
# ==========================================
def vyhodnot_stare_reporty_y_poucit_se():
    os.makedirs("archiv", exist_ok=True)
    dnesni_datum = datetime.datetime.now().strftime("%Y-%m-%d")
    json_soubory = sorted([f for f in os.listdir("archiv" ) if f.endswith(".json")])

    if not json_soubory:
        print("ℹ️ KROK 0: Archiv je zatím prázdný, žádné včerejší reporty k vyhodnocení.")
        return

    for soubor in json_soubory:
        datum_reportu = soubor.replace(".json", "")
        if datum_reportu >= dnesni_datum:
            continue

        cesta_json = os.path.join("archiv", soubor)
        try:
            with open(cesta_json, "r", encoding="utf-8") as f:
                data_reportu = json.load(f)
        except Exception as e:
            print(f"⚠️ Upozornění: Přeskakuji poškozený soubor {cesta_json}: {e}")
            continue

        if data_reportu.get("vyhodnoceno", False):
            continue

        print(f"🔍 KROK 0: Zpětně vyhodnocuji archivovaný report z {datum_reportu}...")

        prompt_vyhodnoceni = f"""
        Jsi nekompromisní auditor sázkařského bota. Zde jsou tipy, které bot vygeneroval dne {datum_reportu}:
        {json.dumps(data_reportu, ensure_ascii=False)}

        TVŮJ ÚKOL PŘES GOOGLE SEARCH:
        1. Dohledej přesné konečné výsledky všech zápasů v sekcích "hlavni" a "alternativni".
        2. Ke každému tipu ponech VŠECHNY původní klíče a přidej klíč "vysledek":
           - Pokud tip vyšel: "✅ VÝHRA (konečné skóre)"
           - Pokud nevyšel: "❌ PROHRA (konečné skóre)"
           - Pokud se nehrálo: "⏳ Nehráno"
        3. U každé prohry zformuluj pravidlo do pole "nove_lekce".

        Odpověz POUZE jako čistý JSON objekt.
        """

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_vyhodnoceni,
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )
            text_odpovedi = response.text
            start_idx = text_odpovedi.find("{")
            end_idx = text_odpovedi.rfind("}")

            if start_idx != -1 and end_idx != -1:
                vyhodnocena_data = json.loads(text_odpovedi[start_idx:end_idx + 1])

                data_reportu["hlavni"] = vyhodnocena_data.get("hlavni", data_reportu.get("hlavni", []))
                data_reportu["alternativni"] = vyhodnocena_data.get("alternativni", data_reportu.get("alternativni", []))
                data_reportu["bilance_souhrn"] = vyhodnocena_data.get("bilance_souhrn", "Vyhodnoceno")
                data_reportu["nove_lekce"] = vyhodnocena_data.get("nove_lekce", [])
                data_reportu["vyhodnoceno"] = True

                with open(cesta_json, "w", encoding="utf-8") as f:
                    json.dump(data_reportu, f, ensure_ascii=False, indent=2)

                cesta_html = os.path.join("archiv", f"{datum_reportu}.html")
                with open(cesta_html, "w", encoding="utf-8") as f:
                    f.write(sestav_html_stranku(datum_reportu, data_reportu))

                if data_reportu["nove_lekce"]:
                    with open("lekce_z_chyb.txt", "a", encoding="utf-8") as f:
                        for lekce in data_reportu["nove_lekce"]:
                            f.write(lekce.strip() + "\n")

                print(f"✅ Report {datum_reportu} vyhodnocen!")
        except Exception as e:
            print(f"⚠️ Nepodařilo se vyhodnotit report z {datum_reportu}: {e}")


# ==========================================
# KROK 1: SCRAPER PRO 30 SPORTŮ
# ==========================================
def stahni_nabidku():
    print("⏳ KROK 1: Robot startuje a stahuje KOMPLETNÍ nabídku z Fortuny...")
    celkovy_text = ""

    vsechny_sporty = [
        ("SPECIÁL BETBUILDER", "https://www.ifortuna.cz/sazeni/betbuilder"),
        ("DNESNI KOMPLETNI NABIDKA", "https://www.ifortuna.cz/sazeni/dnesni-nabidka"),
        ("FOTBAL", "https://www.ifortuna.cz/sazeni/fotbal"),
        ("HOKEJ", "https://www.ifortuna.cz/sazeni/hokej"),
        ("TENIS", "https://www.ifortuna.cz/sazeni/tenis"),
        ("BASKETBAL", "https://www.ifortuna.cz/sazeni/basketbal"),
        ("STOLNÍ TENIS", "https://www.ifortuna.cz/sazeni/stolni-tenis"),
        ("BOJOVÉ SPORTY", "https://www.ifortuna.cz/sazeni/bojove-sporty"),
        ("BOX", "https://www.ifortuna.cz/sazeni/box"),
        ("VOLEJBAL", "https://www.ifortuna.cz/sazeni/volejbal"),
        ("HÁZENÁ", "https://www.ifortuna.cz/sazeni/hazena"),
        ("FLORBAL", "https://www.ifortuna.cz/sazeni/florbal"),
        ("ŠIPKY", "https://www.ifortuna.cz/sazeni/sipky"),
        ("BASEBALL", "https://www.ifortuna.cz/sazeni/baseball"),
        ("AMERICKÝ FOTBAL", "https://www.ifortuna.cz/sazeni/americky-fotbal"),
        ("AUSTRALSKÝ FOTBAL", "https://www.ifortuna.cz/sazeni/australsky-fotbal"),
        ("SNOOKER", "https://www.ifortuna.cz/sazeni/snooker"),
        ("RUGBY", "https://www.ifortuna.cz/sazeni/ragby"),
        ("BADMINTON", "https://www.ifortuna.cz/sazeni/badminton"),
        ("FUTSAL", "https://www.ifortuna.cz/sazeni/futsal"),
        ("KRIKET", "https://www.ifortuna.cz/sazeni/kriket"),
        ("VODNÍ PÓLO", "https://www.ifortuna.cz/sazeni/vodni-polo"),
        ("PLÁŽOVÝ VOLEJBAL", "https://www.ifortuna.cz/sazeni/plazovy-volejbal"),
        ("FORMULE 1", "https://www.ifortuna.cz/sazeni/formule-1"),
        ("MOTOSPORT", "https://www.ifortuna.cz/sazeni/motosport"),
        ("ESPORT CS", "https://www.ifortuna.cz/sazeni/esport-counter-strike"),
        ("ESPORT LOL", "https://www.ifortuna.cz/sazeni/esport-lol"),
        ("ESPORT DOTA2", "https://www.ifortuna.cz/sazeni/esport-dota2"),
        ("ESPORT VALORANT", "https://www.ifortuna.cz/sazeni/esport-valorant")
    ]

    je_na_githubu = os.environ.get("GITHUB_ACTIONS") == "true"
    aktualni_hodina = datetime.datetime.now().hour
    cilova_zalozka = "ZÍTRA" if aktualni_hodina >= 20 else "DNES"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=je_na_githubu, slow_mo=50)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print("🌐 Otevírám Fortunu a potvrzuji Cookies...")
        page.goto("https://www.ifortuna.cz")
        page.wait_for_timeout(4500)

        cookie_selektory = [
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            "#onetrust-accept-btn-handler",
            "button:has-text('Souhlasím')",
            "button:has-text('Přijmout vše')",
            "button:has-text('Povolit vše')"
        ]
        for sel in cookie_selektory:
            try:
                if page.locator(sel).first.is_visible():
                    page.locator(sel).first.click(timeout=1500)
                    page.wait_for_timeout(1000)
                    break
            except:
                pass

        for poradi, (nazev, url) in enumerate(vsechny_sporty, start=1):
            try:
                page.goto(url, timeout=25000)
            except Exception:
                pass

            page.wait_for_timeout(2500)

            if "dnesni-nabidka" not in url and "betbuilder" not in url:
                try:
                    zalozka = page.locator(f"text='{cilova_zalozka}'").first
                    if zalozka.is_visible():
                        zalozka.click(timeout=1500)
                        page.wait_for_timeout(1800)
                except:
                    pass

            for _ in range(6):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(450)

            try:
                surovy_sport_text = page.inner_text("body")
            except:
                continue

            if "Připněte své oblíbené soutěže" in surovy_sport_text:
                surovy_sport_text = surovy_sport_text.split("Připněte své oblíbené soutěže", 1)[-1]
            if "Přivolat tiket" in surovy_sport_text:
                surovy_sport_text = surovy_sport_text.split("Přivolat tiket", 1)[0]

            ciste_radky = [r.strip() for r in surovy_sport_text.splitlines() if r.strip()]
            kompaktni_text = "\n".join(ciste_radky)

            if len(kompaktni_text) > 80:
                celkovy_text += f"\n\n=== KATEGORIE: {nazev} ({url}) ===\n" + kompaktni_text

        browser.close()
        return celkovy_text


# ==========================================
# KROK 2: ROLE GEMINI (VETO FILTR + 0 až N TIPŮ)
# ==========================================
def analyzuj_a_vytvor_data(surovy_text):
    print("🧠 KROK 2: Gemini provádí kontextové VETO kontroly a ověřuje matematickou hodnotu (0 až N tipů)...")

    historicke_lekce = "Zatím žádné zaznamenané chyby z minulých dnů."
    if os.path.exists("lekce_z_chyb.txt"):
        with open("lekce_z_chyb.txt", "r", encoding="utf-8") as f:
            obsah_lekci = f.read().strip()
            if obsah_lekci:
                historicke_lekce = obsah_lekci

    yaml_konfigurace = "Soubor sporty.yaml nebyl nalezen."
    if os.path.exists("sporty.yaml"):
        with open("sporty.yaml", "r", encoding="utf-8") as yf:
            yaml_konfigurace = yf.read()

    prompt = f"""
Jsi špičkový sázkařský kvantitativní analytik a VETO kontrolor skupiny TIPOVACI_BOT.
Matematická hrana (Edge) a fér kurzy jsou dány kurzovou hladinou. 
TVOU HLAVNÍ ROLÍ JE FUNGOVAT JAKO KONTEXTOVÝ VETO FILTR. Odpovídáš na úzkou otázku: 
„Je u zvažovaného zápasu známá informace, která není v kurzu zohledněná? Chybí brankář, klíčová hvězda, jde o B-tým/rezervu, nebo zápas naráží na VETO pravidlo ze sporty.yaml?“

ZÁVAZNÁ KONFIGURACE A PLAYBOOK PRO JEDNOTLIVÉ SPORTY (sporty.yaml):
{yaml_konfigurace}

HISTORICKÉ LEKCE Z VLASTNÍCH CHYB (Těmto chybám se dnes striktně vyhni!):
{historicke_lekce}

DŮLEŽITÁ INSTRUKCE K VÝBĚRU (Pružný počet 0 až N tipů):
- **Žádné povinné počty tipů!** Nevybírej sázky za každou cenu, pokud nesplňují přísná kritéria.
- Procházej nabídku a vybírej POUZE ty příležitosti, kde kurz překonává fér hodnotu a zároveň **prošly kontextovou kontrolou bez VETO**.
- Rozděl je do sekcí "hlavni" (kurz >= 1.80) a "alternativni" (kurz 1.40 - 1.79). Pokud trh nic bezpečného nenabídne, vrať prázdné seznamy `[]`.
- Vždy spočítej minimální hratelný kurz ("sazej_od") a doporučený vklad ("vklad").
- V analýzách vysvětli herní scénář, konkrétní jména z Google Search a výslovně potvrď, že zápas prošel VETO kontrolou!

Odpovědět musíš POUZE v tomto čistém JSON formátu (ZÁKAZ používat Markdown tagy):
{{
  "hlavni": [
    {{"zapas": "Tým A vs Tým B (Sport)", "tip": "Konkrétní tip", "kurz": "1.95", "sazej_od": "1.85", "vklad": "2.0/10", "duvera": "9", "uspesnost": "58 %"}}
  ],
  "alternativni": [],
  "analyzy": [
    {{"nadpis": "ZÁPAS: Tým A vs Tým B (Sport)", "text": "Hutný analytický text potvrzující VETO kontrolu a kontext..."}}
  ]
}}

KOMPLETNÍ DATA ZE SÁZKOVKY K ANALÝZE:
{surovy_text[:2000000]}
"""

    # Opraveno na podporovaný model podle chybové hlášky z logů
    modely_k_vyzkouseni = ["gemini-3.8-flash", "gemini-3.1-pro-preview"]

    for pokus, aktualni_model in enumerate(modely_k_vyzkouseni, start=1):
        try:
            print(f"🚀 Odesílám data do modelu: {aktualni_model} (Pokus {pokus})...")
            response = client.models.generate_content(
                model=aktualni_model,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )

            text_odpovedi = response.text
            start_idx = text_odpovedi.find("{")
            end_idx = text_odpovedi.rfind("}")

            if start_idx != -1 and end_idx != -1:
                return json.loads(text_odpovedi[start_idx:end_idx + 1])
        except Exception as e:
            print(f"⏳ Chyba modelu ({e}). Čekám 10 vteřin...")
            time.sleep(10)

    return {"hlavni": [], "alternativni": [], "analyzy": []}


# ==========================================
# KROK 3: TVORBA HTML, ZÁLOHY A ODESLÁNÍ NA WHATSAPP
# ==========================================
def vytvor_html_zalohuj_ai_publikuj(data_json):
    if not data_json:
        data_json = {"hlavni": [], "alternativni": [], "analyzy": []}

    dnesni_datum = datetime.datetime.now().strftime("%Y-%m-%d")
    data_json["vyhodnoceno"] = False

    html_obsah = sestav_html_stranku(dnesni_datum, data_json)

    os.makedirs("archiv", exist_ok=True)
    with open(f"archiv/{dnesni_datum}.html", "w", encoding="utf-8") as f:
        f.write(html_obsah)
    with open(f"archiv/{dnesni_datum}.json", "w", encoding="utf-8") as f:
        json.dump(data_json, f, ensure_ascii=False, indent=2)
    with open("dnesni_report.html", "w", encoding="utf-8") as f:
        f.write(html_obsah)

    aktualizuj_rozcestnik_archivu(dnesni_datum)

    odkaz_na_report = f"{github_pages_url}/archiv/{dnesni_datum}.html"
    odesli_na_whatsapp(data_json, dne_datum=dnesni_datum, url_reportu=odkaz_na_report)


def aktualizuj_rozcestnik_archivu(dnesni_datum):
    soubory = sorted([f for f in os.listdir("archiv") if f.endswith(".html")], reverse=True)
    polozky_archivu = ""
    for s in soubory:
        datum_s = s.replace(".html", "")
        cesta_j = os.path.join("archiv", f"{datum_s}.json")
        bilance_text = "⏳ Čeká na vyhodnocení"
        if os.path.exists(cesta_j):
            try:
                with open(cesta_j, "r", encoding="utf-8") as jf:
                    jdata = json.load(jf)
                    if jdata.get("vyhodnoceno", False):
                        bilance_text = f"✅ {jdata.get('bilance_souhrn', 'Vyhodnoceno')}"
            except:
                pass
        polozky_archivu += (
            f"<li style='margin: 12px 0; font-size: 17px;'>"
            f"<a href='archiv/{s}' style='color: #007bff; text-decoration: none; font-weight: bold;'>"
            f"📅 HTML Report a Záloha – {datum_s}</a> "
            f"<span style='color: #555; font-size: 15px;'>({bilance_text})</span>"
            f"</li>\n"
        )

    lekce_html = "<li>Zatím žádné zaznamenané chyby.</li>"
    if os.path.exists("lekce_z_chyb.txt"):
        with open("lekce_z_chyb.txt", "r", encoding="utf-8") as lf:
            radky = [r.strip() for r in lf.readlines() if r.strip()]
            if radky:
                lekce_html = "".join([f"<li style='margin-bottom: 6px;'>{r}</li>\n" for r in reversed(radky[-20:])])

    index_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Sklad HTML Reportů a Paměť Chyb | TIPOVACI_BOT</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px; color: #333; }}
        .container {{ max-width: 850px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1); }}
        h1 {{ color: #1a1a1a; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #1a1a1a; margin-top: 30px; }}
        .btn-today {{ display: inline-block; background: #28a745; color: #ffffff; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 18px; margin: 10px 0 20px 0; }}
        .memory-box {{ background: #fff8e6; border-left: 5px solid #ffc107; padding: 15px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Sklad HTML Reportů (TIPOVACI_BOT)</h1>
        <a href="archiv/{dnesni_datum}.html" class="btn-today">🔥 Otevřít dnešní report ({dnesni_datum})</a>
        <h2>🗂️ Záloha všech historických HTML reportů</h2>
        <ul>{polozky_archivu}</ul>
        <h2>🧠 Paměť bota: Naučené lekce z vlastních chyb</h2>
        <div class="memory-box"><ul>{lekce_html}</ul></div>
    </div>
</body>
</html>"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(index_html)


def odesli_na_whatsapp(data_json, dne_datum, url_reportu):
    if not (wa_instance and wa_token and wa_group_id):
        print("ℹ️ WhatsApp údaje nejsou nastaveny – odkaz je uložen na GitHubu.")
        return

    hlavni_tipy = data_json.get("hlavni", [])
    radky_zpravy = []
    
    if hlavni_tipy:
        for t in hlavní_tipy:
            sazej_od = t.get("sazej_od", t.get("kurz"))
            vklad = t.get("vklad", "1.5/10")
            radky_zpravy.append(
                f"🔹 *{t.get('zapas')}*\n"
                f"   👉 {t.get('tip')}\n"
                f"   📊 Kurz: *{t.get('kurz')}* | Sázej od: *{sazej_od}+* | Vklad: *{vklad}*"
            )
        prehled_hlavni = "\n".join(radky_zpravy)
        sekce_zpravy = f"🔥 *SCHVÁLENÉ VALUE TIPY ({len(hlavni_tipy)}):*\n{prehled_hlavni}"
    else:
        sekce_zpravy = "⚠️ *Dnes nebyla nalezena žádná sázka bez VETO rizika.* Trpělivost je součástí strategie."

    zprava = (
        f"🤖 *TIPOVACI_BOT | Ranní Report ({dne_datum})*\n\n"
        f"{sekce_zpravy}\n\n"
        f"📊 *Kompletní HTML report (vč. VETO analýz):*\n"
        f"🔗 {url_reportu}\n\n"
        f"🗂 *Archiv všech HTML záloh a vyhodnocení chyb:*\n"
        f"🔗 {github_pages_url}/"
    )

    api_url = f"https://api.green-api.com/waInstance{wa_instance}/sendMessage/{wa_token}"
    payload = json.dumps({"chatId": wa_group_id, "message": zprava}).encode("utf-8")
    req = urllib.request.Request(api_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            print("✅ Zpráva úspěšně odeslána do WhatsApp skupiny!")
    except Exception as e:
        print(f"❌ Chyba při odesílání na WhatsApp: {e}")


if __name__ == "__main__":
    dnesni_datum = datetime.datetime.now().strftime('%Y-%m-%d')
    cesta_dnesni_json = f"archiv/{dnesni_datum}.json"

    if os.environ.get("RESEND_WA_ONLY") == "true":
        if os.path.exists(cesta_dnesni_json):
            with open(cesta_dnesni_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            odesli_na_whatsapp(data, dnesni_datum, f"{github_pages_url}/archiv/{dnesni_datum}.html")
    else:
        vyhodnot_stare_reporty_y_poucit_se()
        cesta_dnesni_html = f"archiv/{dnesni_datum}.html"
        # Pro jistotu pro test vymažeme kontrolu existence, aby se spolehlivě provedla analýza
        text_nabidky = stahni_nabidku()
        if len(text_nabidky) > 5000:
            data = analyzuj_a_vytvor_data(text_nabidky)
            vytvor_html_zalohuj_ai_publikuj(data)
