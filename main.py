import os
import json
import time
import datetime
import urllib.request
from dotenv import load_dotenv
from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

# ==========================================
# 0. NAČTENÍ CITLIVÝCH ÚDAJŮ (Z .ENV NEBO GITHUB SECRETS)
# ==========================================
load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

# Volitelné údaje pro WhatsApp (Green-API) a URL tvého GitHub skladu
wa_instance = os.environ.get("WA_INSTANCE_ID")
wa_token = os.environ.get("WA_API_TOKEN")
wa_group_id = os.environ.get("WA_GROUP_ID")
github_pages_url = os.environ.get("GITHUB_PAGES_URL", "https://tvoje-jmeno.github.io/TipovaciBot")

client = genai.Client(api_key=api_key)


# ==========================================
# POMOCNÁ FUNKCE: KOMPLETNÍ HTML ŠABLONA REPORTU
# ==========================================
def sestav_html_stranku(datum_str, data_json):
    """Vytvoří kompletní HTML report (pro nový den i pro aktualizaci zálohy po vyhodnocení)."""
    radky_hlavni = ""
    for t in data_json.get("hlavni", []):
        zapas = t.get("zapas", "Neznámý zápas")
        tip = t.get("tip", "-")
        kurz = t.get("kurz", "-")
        duvera = t.get("duvera", "-")
        uspesnost = t.get("uspesnost", "-")
        stav = t.get("vysledek", "⏳ Čeká na výsledek")
        barva = "#28a745" if "✅" in stav else ("#dc3545" if "❌" in stav else "#6c757d")
        radky_hlavni += (
            f"«tr»"
            f"«td»«span class='tip'»{zapas}:«/span» {tip}«/td»"
            f"«td class='odds'»{kurz}«/td»"
            f"«td»{duvera}«/td»"
            f"«td»{uspesnost}«/td»"
            f"«td style='font-weight: bold; color: {barva};'»{stav}«/td»"
            f"«/tr»\n"
        )

    radky_alt = ""
    for t in data_json.get("alternativni", []):
        zapas = t.get("zapas", "Neznámý zápas")
        tip = t.get("tip", "-")
        kurz = t.get("kurz", "-")
        duvera = t.get("duvera", "-")
        uspesnost = t.get("uspesnost", "-")
        stav = t.get("vysledek", "⏳ Čeká na výsledek")
        barva = "#28a745" if "✅" in stav else ("#dc3545" if "❌" in stav else "#6c757d")
        radky_alt += (
            f"«tr»"
            f"«td»«span class='tip'»{zapas}:«/span» {tip}«/td»"
            f"«td class='odds'»{kurz}«/td»"
            f"«td»{duvera}«/td»"
            f"«td»{uspesnost}«/td»"
            f"«td style='font-weight: bold; color: {barva};'»{stav}«/td»"
            f"«/tr»\n"
        )

    analyzy_html = ""
    for a in data_json.get("analyzy", []):
        nadpis = a.get("nadpis", "Analýza zápasu")
        text = a.get("text", "")
        analyzy_html += f"«h3»{nadpis}«/h3»\n«p»{text}«/p»\n"

    box_vyhodnoceni = ""
    if data_json.get("vyhodnoceno", False):
        bilance = data_json.get("bilance_souhrn", "Vyhodnoceno")
        seznam_lekci = data_json.get("nove_lekce", [])
        if seznam_lekci:
            polozky_lekci = "".join([f"«li»{lekce}«/li»" for lekce in seznam_lekci])
        else:
            polozky_lekci = "«li»Žádné kritické chyby v tento den.«/li»"

        box_vyhodnoceni = f"""
        «div class="eval-box"»
            «h3»📊 Zpětné vyhodnocení dne: {bilance}«/h3»
            «p»«strong»Zapsané lekce z chyb do paměti bota:«/strong»«/p»
            «ul»
                {polozky_lekci}
            «/ul»
        «/div»
        """

    html_dokument = f"""«!DOCTYPE html»
«html»
«head»
    «title»Ranní Sportovní Report pro Investory ({datum_str})«/title»
    «meta charset="UTF-8"»
    «meta name="viewport" content="width=device-width, initial-scale=1.0"»
    «style»
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f4f4f4;
            color: #333;
        }}
        .container {{
            max-width: 850px;
            margin: 0 auto;
            background-color: #ffffff;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }}
        h1 {{
            color: #1a1a1a;
            font-size: 24px;
            margin-bottom: 20px;
            text-align: center;
        }}
        h2 {{
            color: #1a1a1a;
            font-size: 20px;
            margin-top: 30px;
            margin-bottom: 15px;
            border-bottom: 1px solid #eee;
            padding-bottom: 5px;
        }}
        h3 {{
            color: #333;
            font-size: 18px;
            margin-top: 25px;
            margin-bottom: 10px;
        }}
        p {{
            line-height: 1.6;
            margin-bottom: 15px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
            font-size: 14px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
            font-weight: bold;
            color: #555;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .tip {{
            font-weight: bold;
            color: #007bff;
        }}
        .odds {{
            color: #28a745;
            font-weight: bold;
        }}
        .back-link {{
            display: inline-block;
            margin-bottom: 15px;
            color: #007bff;
            text-decoration: none;
            font-weight: bold;
        }}
        .eval-box {{
            background-color: #eef6ff;
            border-left: 5px solid #007bff;
            padding: 15px;
            margin-bottom: 25px;
            border-radius: 4px;
        }}
        .eval-box h3 {{
            margin-top: 0;
            color: #0056b3;
        }}
    «/style»
«/head»
«body»
    «div class="container"»
        «a href="../index.html" class="back-link"»⬅ Zpět do hlavního skladu všech HTML reportů«/a»
        «h1»Ranní Sportovní Report pro Investory ({datum_str})«/h1»
        {box_vyhodnoceni}
        «p»Vážení investoři ze skupiny «strong»TIPOVACI_BOT«/strong»,«/p»
        «p»přinášíme vám náš ranní report s dnešními klíčovými sázkovými příležitostmi, podloženými hloubkovou analýzou nejnovějších dostupných informací a napojenými na paměť předchozích chyb. Naším cílem je vyhledávat Bet Value napříč celým sportovním spektrem za využití specifických postupů pro každý sport.«/p»

        «h2»Hlavní tipy (kurz >= 1.80)«/h2»
        «table»
            «thead»
                «tr»
                    «th»Příležitost«/th»
                    «th»Kurz«/th»
                    «th»Důvěra (1-10)«/th»
                    «th»Úspěšnost (%)«/th»
                    «th»Výsledek«/th»
                «/tr»
            «/thead»
            «tbody»
                {radky_hlavni}
            «/tbody»
        «/table»

        «h2»Alternativní tipy (kurz 1.40 - 1.79)«/h2»
        «table»
            «thead»
                «tr»
                    «th»Příležitost«/th»
                    «th»Kurz«/th»
                    «th»Důvěra (1-10)«/th»
                    «th»Úspěšnost (%)«/th»
                    «th»Výsledek«/th»
                «/tr»
            «/thead»
            «tbody»
                {radky_alt}
            «/tbody»
        «/table»

        «h2»Detailní analýzy zápasů«/h2»
        {analyzy_html}

        «p»S pozdravem,«/p»
        «p»«strong»Váš Tým Sportovních Analytiků (TIPOVACI_BOT)«/strong»«/p»
    «/div»
«/body»
«/html»"""
    return html_dokument.replace("«", "\x3c").replace("»", "\x3e")


# ==========================================
# KROK 0: ZPĚTNÉ VYHODNOCENÍ ARCHIVU A UČENÍ Z CHYB
# ==========================================
def vyhodnot_stare_reporty_a_poucit_se():
    os.makedirs("archiv", exist_ok=True)
    dnesni_datum = datetime.datetime.now().strftime("%Y-%m-%d")
    json_soubory = sorted([f for f in os.listdir("archiv") if f.endswith(".json")])

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
            print(f"⚠️ Chyba při čtení {cesta_json}: {e}")
            continue

        if data_reportu.get("vyhodnoceno", False):
            continue

        print(f"🔍 KROK 0: Zpětně vyhodnocuji archivovaný report z {datum_reportu} a hledám chyby...")

        prompt_vyhodnoceni = f"""
        Jsi nekompromisní auditor sázkařského bota. Zde jsou tipy, které bot vygeneroval dne {datum_reportu}:
        {json.dumps(data_reportu, ensure_ascii=False)}

        TVŮJ ÚKOL PŘES GOOGLE SEARCH:
        1. Dohledej přesné konečné výsledky všech zápasů v sekcích "hlavni" a "alternativni".
        2. Ke každému tipu v poli "hlavni" i "alternativni" ponech původní klíče ("zapas", "tip", "kurz", "duvera", "uspesnost") a přidej klíč "vysledek":
           - Pokud tip vyšel, nastav hodnotu: "✅ VÝHRA (konečné skóre)"
           - Pokud tip nevyšel, nastav hodnotu: "❌ PROHRA (konečné skóre)"
           - Pokud se zápas ještě neodehrál, nastav hodnotu: "⏳ Nehráno"
        3. U každé "❌ PROHRA" zjisti z pozápasových statistik, PROČ sázka nevyšla (např. kolísavá forma týmu jako na sinusoidě, chyběl 1 roh či gól, podcenění únavy, červená karta) a zformuluj z toho konkrétní pravidlo do pole "nove_lekce".

        Odpověz POUZE jako čistý JSON objekt v této přesné struktuře (žádné Markdown značky):
        {{
          "hlavni": [
            {{"zapas": "Název zápasu", "tip": "Původní tip", "kurz": "1.95", "duvera": "9", "uspesnost": "85 %", "vysledek": "✅ VÝHRA (2:1)"}}
          ],
          "alternativni": [
            {{"zapas": "Název zápasu", "tip": "Původní tip", "kurz": "1.65", "duvera": "7", "uspesnost": "70 %", "vysledek": "❌ PROHRA (0:0)"}}
          ],
          "bilance_souhrn": "7 výher / 3 prohry (Úspěšnost 70 %)",
          "nove_lekce": [
            "[{datum_reportu}] POZOR: Konkrétní ponaučení z prohraného zápasu pro příští analýzy."
          ]
        }}
        """

        try:
            response = client.models.generate_content(
                model="gemini-3.1-pro-preview",
                contents=prompt_vyhodnoceni,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
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

                print(f"✅ Report {datum_reportu} vyhodnocen ({data_reportu['bilance_souhrn']}) a lekce uloženy do paměti!")
        except Exception as e:
            print(f"⚠️ Nepodařilo se automaticky vyhodnotit report z {datum_reportu}: {e}")


# ==========================================
# KROK 1: KOMPLETNÍ SCRAPER VŠECH SPORTŮ NA FORTUNĚ
# ==========================================
def stahni_nabidku():
    print("⏳ KROK 1: Robot startuje a stahuje KOMPLETNÍ nabídku všech sportů z Fortuny...")
    celkovy_text = ""

    vsechny_sporty = [
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
            "button:has-text('Povolit vše')",
            "text=Souhlasím",
            "text=Přijmout vše"
        ]
        for sel in cookie_selektory:
            try:
                if page.locator(sel).first.is_visible():
                    page.locator(sel).first.click(timeout=1500)
                    print("🍪 Cookies lišta úspěšně potvrzena.")
                    page.wait_for_timeout(1000)
                    break
            except:
                pass

        for _ in range(3):
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        for poradi, (nazev, url) in enumerate(vsechny_sporty, start=1):
            print(f"👉 [{poradi}/{len(vsechny_sporty)}] Stahuji kurzy pro: {nazev}...")
            try:
                page.goto(url, timeout=25000)
            except Exception:
                print(f"⚠️ Sekce {nazev} se načítala příliš dlouho, zkouším pokračovat...")

            page.wait_for_timeout(2500)

            if "dnesni-nabidka" not in url:
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

            for t_text in ["Zobrazit více", "Zobrazit další", "Načíst další"]:
                try:
                    tlacitka = page.locator(f"text={t_text}").all()
                    for t in tlacitka:
                        if t.is_visible():
                            t.click(timeout=800)
                            page.wait_for_timeout(400)
                except:
                    pass

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

        print(f"✅ KOMPLETNĚ STAŽENO: {len(celkovy_text)} znaků kurzové nabídky napříč sporty.")
        with open("stazena_data_debug.txt", "w", encoding="utf-8") as f:
            f.write(celkovy_text)

        return celkovy_text


# ==========================================
# KROK 2: AI ANALÝZA (MODEL GEMINI 3.1 PRO + PAMĚŤ CHYB + PLAYBOOK)
# ==========================================
def analyzuj_a_vytvor_data(surovy_text):
    print("🧠 KROK 2: AI (Tier 1 Prepay) načítá historické chyby a aplikuje sázkařský playbook...")

    historicke_lekce = "Zatím žádné zaznamenané chyby z minulých dnů."
    if os.path.exists("lekce_z_chyb.txt"):
        with open("lekce_z_chyb.txt", "r", encoding="utf-8") as f:
            obsah_lekci = f.read().strip()
            if obsah_lekci:
                historicke_lekce = obsah_lekci

    prompt = f"""
    Jsi elitní sázkařský analytik skupiny TIPOVACI_BOT, který má k dispozici kompletní nabídku všech sportů ze sázkové kanceláře a učí se z vlastních chyb.
    Projdi úplně všechny kategorie v dodaných datech a vyber 10 NEJLEPŠÍCH UNIKÁTNÍCH TIPŮ:
    - 5x Hlavní tipy s kurzem >= 1.80 (tvrdá Bet Value)
    - 5x Alternativní tipy s kurzem v rozmezí 1.40 až 1.79

    STRIKTNÍ PRAVIDLA PRO VÝBĚR ZÁPASŮ:
    1. ZÁKAZ LIVE ZÁPASŮ: Nikdy nevybírej zápasy, které už probíhají (mají u sebe uvedeno např. "1. set", "2. set", "3. tř.", "1. čt." nebo průběžné skóre). Vybírej POUZE zápasy před výkopem, které mají uvedený čas začátku ("dnes HH:MM" nebo "zítra HH:MM")!
    2. POUZE NEJBLIŽŠÍ ZÁPASY (DNES / ZÍTRA): Nevybírej zápasy, které se hrají za týden nebo za měsíc.
    3. DIVERZITA SPORTŮ: Maximálně 2 až 3 zápasy ze stejného sportu. Využij celou šíři nabídky (fotbal, hokej, tenis, basketbal, stolní tenis, šipky, MMA, box, volejbal, házená, florbal, baseball, snooker, esport atd.). Každý ze 10 tipů musí být z jiného utkání.
    4. NEUTRÁLNÍ PŮDA: U mezinárodních turnajů nikdy neargumentuj výhodou domácího prostředí.

    HISTORICKÉ LEKCE Z VLASTNÍCH CHYB (Těmto chybám se dnes striktně vyhni!):
    {historicke_lekce}

    TVRDÁ PRAVIDLA PRO PSANÍ ANALÝZY (ZÁKAZ OBYČEJNÝCH FRÁZÍ):
    Tvé analýzy nesmí obsahovat žádnou "omáčku", klišé ani podmiňovací způsoby. Žádné fráze jako "Pokud zahrají dobře...", "Mají šanci na výhru...", "Je to silný tým...".
    Musíš jít do absolutní hloubky. Musíš použít Google Search a do každé analýzy zakomponovat KONKRÉTNÍ jména, KONKRÉTNÍ zranění, statistiky a konzistenci formy (pozor na týmy s formou jako na sinusoidě!).

    VZOR TVÉHO STYLU (Takhle musí vypadat tón tvého textu):
    "Sázka na vítězství stojí na mimořádně silném základu. Ofenziva je variabilní – quarterback hraje nejvyzrálejší úsek kariéry a má k dispozici elitní cíle v podobě Smithe-Njigby (ocenění útočník roku v kapse). Významným prvkem je i precizní obrana, která se etablovala jako číslo jedna a vysloužila si přezdívku 'Dark Side'. Naopak soupeř se potýká s absencí klíčového levého obránce kvůli trhlině v hamstringu, což absolutně zničí jejich rozehrávku."

    SÁZKAŘSKÝ PLAYBOOK (CO HLEDAT PŘES GOOGLE PRO KONKRÉTNÍ SPORTY):
    - [FOTBAL / FUTSAL]: Hledej rotace v kádru, zranění brankářů/stoperů, data o xG (očekávané góly), výkyvy formy po reprezentačních či pohárových zápasech.
    - [HOKEJ / FLORBAL]: Zásadní je potvrdit startujícího brankáře přes Google (jednička vs. náhradník). Dále hledej únavu z B2B (zápasy dva dny po sobě) a efektivitu přesilovek.
    - [BASKETBAL / HÁZENÁ / VOLEJBAL]: Hledej "load management" (odpočívající opory), tempo hry (pace), rotaci sestavy, doskoky a cestovní únavu.
    - [TENIS / STOLNÍ TENIS / BADMINTON]: Zkoumej přesnou H2H bilanci, extrémní preferenci povrchu (tráva, antuka, hard), únavu z předchozích maratonských zápasů a bilanci z posledních 10 utkání.
    - [BOJOVÉ SPORTY (MMA / BOX)]: Analyzuj H2H styl (striker vs. wrestler/grappler), rozpětí paží (reach), kardio v pozdějších kolech a problémy při shazování váhy.
    - [ŠIPKY / SNOOKER / BASEBALL / ESPORT]: V baseballu porovnej startující nadhazovače (ERA, WHIP), v šipkách průměry na 3 šipky (3-dart average) a úspěšnost zavírání (checkout %), v esportu aktuální map pool a nedávné změny v sestavě (rosteru).

    Odpověz POUZE v tomto čistém JSON formátu (včetně uvozovek a závorek, ZÁKAZ používat Markdown tagy):
    {{
      "hlavni": [
        {{"zapas": "Tým A vs Tým B (Sport)", "tip": "Výhra Tým A", "kurz": "1.95", "duvera": "9", "uspesnost": "85 %"}}
      ],
      "alternativni": [
        {{"zapas": "Tým C vs Tým D (Sport)", "tip": "Více než 2.5 gólu", "kurz": "1.65", "duvera": "7", "uspesnost": "70 %"}}
      ],
      "analyzy": [
        {{"nadpis": "ZÁPAS: Tým A vs Tým B (Sport)", "text": "Zde bude hutný, detailní text o 4-5 větách napěchovaný jmény, čísly a statistikami..."}}
      ]
    }}

    KOMPLETNÍ DATA ZE SÁZKOVKY K ANALÝZE:
    {surovy_text[:2000000]}
    """

    # Aktuální modely vyžadované Googlem pro nové projekty (Tier 1 Prepay)
    modely_k_vyzkouseni = ["gemini-3.1-pro-preview", "gemini-3.1-pro-preview", "gemini-3-flash"]

    for pokus, aktualni_model in enumerate(modely_k_vyzkouseni, start=1):
        try:
            print(f"🚀 Odesílám data do placeného modelu: {aktualni_model} (Pokus {pokus}/{len(modely_k_vyzkouseni)})...")
            response = client.models.generate_content(
                model=aktualni_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )

            text_odpovedi = response.text
            start_idx = text_odpovedi.find("{")
            end_idx = text_odpovedi.rfind("}")

            if start_idx != -1 and end_idx != -1:
                cisty_json = text_odpovedi[start_idx:end_idx + 1]
                print(f"✅ Analýza úspěšně dokončena modelem {aktualni_model}!")
                return json.loads(cisty_json)
            else:
                print(f"⚠️ Model {aktualni_model} nevrátil čistý JSON, zkouším další pokus...")

        except Exception as e:
            print(f"⏳ Server modelu {aktualni_model} vrátil chybu ({e}). Čekám 10 vteřin a zkouším znovu...")
            time.sleep(10)

    print("❌ Chyba: Nepodařilo se získat analýzu po všech pokusech.")
    return None


# ==========================================
# KROK 3: TVORBA HTML, ZÁLOHY V ARCHIVU A ROZCESTNÍKU NA GITHUBU
# ==========================================
def vytvor_html_zalohuj_a_publikuj(data_json):
    if not data_json:
        return

    print("📁 KROK 3: Vytvářím dnešní HTML report a ukládám trvalou HTML zálohu do archivu...")

    dnesni_datum = datetime.datetime.now().strftime("%Y-%m-%d")
    data_json["vyhodnoceno"] = False

    html_obsah = sestav_html_stranku(dnesni_datum, data_json)

    os.makedirs("archiv", exist_ok=True)
    cesta_html_zaloha = f"archiv/{dnesni_datum}.html"
    cesta_json_zaloha = f"archiv/{dnesni_datum}.json"

    with open(cesta_html_zaloha, "w", encoding="utf-8") as f:
        f.write(html_obsah)
    with open(cesta_json_zaloha, "w", encoding="utf-8") as f:
        json.dump(data_json, f, ensure_ascii=False, indent=2)

    with open("dnesni_report.html", "w", encoding="utf-8") as f:
        f.write(html_obsah)

    aktualizuj_rozcestnik_archivu(dnesni_datum)

    odkaz_na_report = f"{github_pages_url}/archiv/{dnesni_datum}.html"
    print(f"✅ HTML report i záloha uloženy: {cesta_html_zaloha}")
    print(f"🌐 Veřejný odkaz pro skupinu: {odkaz_na_report}")

    odesli_na_whatsapp(data_json, dne_datum=dnesni_datum, url_reportu=odkaz_na_report)


def aktualizuj_rozcestnik_archivu(dnesni_datum):
    """Vytvoří hlavní webovou stránku index.html se seznamem všech HTML záloh a deníkem chyb."""
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
            f"«li style='margin: 12px 0; font-size: 17px;'»"
            f"«a href='archiv/{s}' style='color: #007bff; text-decoration: none; font-weight: bold;'»"
            f"📅 HTML Report a Záloha – {datum_s}«/a» "
            f"«span style='color: #555; font-size: 15px;'»({bilance_text})«/span»"
            f"«/li»\n"
        )

    lekce_html = "«li»Zatím žádné zaznamenané chyby – bot čeká na vyhodnocení prvních zápasů.«/li»"
    if os.path.exists("lekce_z_chyb.txt"):
        with open("lekce_z_chyb.txt", "r", encoding="utf-8") as lf:
            radky = [r.strip() for r in lf.readlines() if r.strip()]
            if radky:
                lekce_html = "".join([f"«li style='margin-bottom: 6px;'»{r}«/li»\n" for r in reversed(radky[-20:])])

    index_html = f"""«!DOCTYPE html»
«html»
«head»
    «title»Sklad HTML Reportů a Paměť Chyb | TIPOVACI_BOT«/title»
    «meta charset="UTF-8"»
    «meta name="viewport" content="width=device-width, initial-scale=1.0"»
    «style»
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 850px;
            margin: 0 auto;
            background: #ffffff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }}
        h1 {{
            color: #1a1a1a;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #1a1a1a;
            margin-top: 30px;
        }}
        .btn-today {{
            display: inline-block;
            background: #28a745;
            color: #ffffff;
            padding: 12px 20px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
            font-size: 18px;
            margin: 10px 0 20px 0;
        }}
        .memory-box {{
            background: #fff8e6;
            border-left: 5px solid #ffc107;
            padding: 15px;
            border-radius: 4px;
        }}
    «/style»
«/head»
«body»
    «div class="container"»
        «h1»🤖 Sklad HTML Reportů (TIPOVACI_BOT)«/h1»
        «a href="archiv/{dnesni_datum}.html" class="btn-today"»🔥 Otevřít dnešní report ({dnesni_datum})«/a»

        «h2»🗂️ Záloha všech historických HTML reportů«/h2»
        «ul»
            {polozky_archivu}
        «/ul»

        «h2»🧠 Paměť bota: Naučené lekce z vlastních chyb«/h2»
        «div class="memory-box"»
            «ul»
                {lekce_html}
            «/ul»
        «/div»
    «/div»
«/body»
«/html»"""
    ciste_index_html = index_html.replace("«", "\x3c").replace("»", "\x3e")
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(ciste_index_html)


def odesli_na_whatsapp(data_json, dne_datum, url_reportu):
    """Odešle přehled a odkaz na HTML report přímo do WhatsApp skupiny TIPOVACI_BOT."""
    if not (wa_instance and wa_token and wa_group_id):
        print("ℹ️ WhatsApp údaje (WA_INSTANCE_ID, WA_API_TOKEN, WA_GROUP_ID) zatím nejsou nastaveny – odkaz je uložen na GitHubu.")
        return

    print("📲 Posílám odkaz na dnešní HTML report do WhatsApp skupiny TIPOVACI_BOT...")
    radky_zpravy = []
    for t in data_json.get("hlavni", []):
        radky_zpravy.append(
            f"🔹 *{t.get('zapas')}*\n   👉 {t.get('tip')} (Kurz: *{t.get('kurz')}* | Důvěra: {t.get('duvera')}/10)"
        )
    prehled_hlavni = "\n".join(radky_zpravy)

    zprava = (
        f"🤖 *TIPOVACI_BOT | Ranní Report ({dne_datum})*\n\n"
        f"🔥 *TOP 5 VALUE TIPŮ (Kurz >= 1.80):*\n"
        f"{prehled_hlavni}\n\n"
        f"📊 *Kompletní HTML report s analýzami:*\n"
        f"🔗 {url_reportu}\n\n"
        f"🗂 *Archiv všech HTML záloh a vyhodnocení chyb:*\n"
        f"🔗 {github_pages_url}/"
    )

    api_url = f"https://api.green-api.com/waInstance{wa_instance}/sendMessage/{wa_token}"
    payload = json.dumps({"chatId": wa_group_id, "message": zprava}).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            print("✅ Zpráva s odkazem na HTML report úspěšně odeslána do skupiny TIPOVACI_BOT!")
    except Exception as e:
        print(f"❌ Chyba při odesílání na WhatsApp: {e}")


# ==========================================
# HLAVNÍ SPOUŠTĚČ SKRIPTU
# ==========================================
if __name__ == "__main__":
    print("🤖 Spouštím TipovaciBot (Krok 0: Učení z chyb -> Krok 1: Fortuna -> Krok 2: AI 3.1 Pro -> Krok 3: HTML & Záloha)...")
    vyhodnot_stare_reporty_a_poucit_se()
    text_nabidky = stahni_nabidku()
    if len(text_nabidky) > 5000:
        data = analyzuj_a_vytvor_data(text_nabidky)
        vytvor_html_zalohuj_a_publikuj(data)
    else:
        print("⚠️ KRITICKÁ CHYBA: Málo dat ke zpracování.")