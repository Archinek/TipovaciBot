# 🤖 TIPOVACI_BOT

Každé ráno v 8:00 (Praha) pošle do WhatsApp skupiny seznam zápasů, u kterých existuje kurzová hrana,
a **kurz, od kterého se sázka vyplatí**. Zbytek dne měří, jestli to fungovalo (CLV, ROI).

## Jak to funguje

```
08:00  morning.yml
        1. vyhodnotí včerejší tipy (výsledky z Odds API /scores)
        2. stáhne kurzy (Odds API) pro sporty ze sporty.yaml
        3. engine.py: férová pravděpodobnost z Pinnacle (bez marže)
           vs. nejlepší kurz ostatních kanceláří -> edge
        4. Gemini = jen KONTROLA RIZIK (OK / VETO / NEJISTE), nehledá hranu
        5. zapíše do data/bety.csv, vytvoří docs/reports/DATUM.html a pošle WhatsApp

každých 30 min  closing.yml
        zápasům < 80 min před výkopem uloží uzavírací fér kurz -> CLV
```

**Režimy sportů** (v `sporty.yaml`, `vychozi_rezim`):
`paper` = jen sleduj (zpráva říká „SLEDOVAT"), `live` = sázet („SÁZET od kurzu X"), `off` = vypnuto.
Všechno začíná jako `paper`. Přepni na `live`, až ti `avg_clv` v reportu ukáže, že to dává smysl.

## Nasazení (cca 15 minut)

1. **Nový repozitář** na GitHubu, nahraj sem obsah této složky (včetně `.github/`).
2. **Settings → Secrets and variables → Actions → Secrets**:

   | Secret | Odkud |
   |---|---|
   | `ODDS_API_KEY` | https://the-odds-api.com (registrace, klíč do e-mailu) |
   | `GEMINI_API_KEY` | tvůj stávající |
   | `WA_INSTANCE_ID`, `WA_API_TOKEN`, `WA_GROUP_ID` | tvoje stávající z Green API |

   **Variables** (nepovinné): `WA_API_URL` (pokud tvá instance v Green API konzoli ukazuje
   vlastní `apiUrl`, např. `https://7105.api.greenapi.com`; výchozí je `https://api.green-api.com`),
   `PAGES_URL`, `GEMINI_MODEL`.
3. **Settings → Pages**: Source = *Deploy from a branch*, branch `main`, složka **`/docs`**.
4. **Settings → Actions → General → Workflow permissions** = *Read and write permissions*.
5. **Actions → Ranní report → Run workflow → akce `sports`**: vypíše, které sporty Odds API
   vrací a které se ti namapovaly. Co nesedí, uprav v `sporty.yaml` (`groups`).
6. **Run workflow → akce `morning`**: ruční ostrý běh (ignoruje časové okno). Zkontroluj WhatsApp a Pages.
7. Dál běží samo.

> ⚠️ **Veřejný repozitář = veřejné reporty a `bety.csv`.** Privátní repo má Pages jen na placených plánech.

## Kredity Odds API (důležité)

- `/sports` a `/events` jsou zdarma, `/odds` stojí kredit za každý sport-klíč a region, `/scores` 2 kredity.
- Bot nejdřív zdarma zjistí, jestli sport-klíč má zápasy v okně 36 h, a platí jen za neprázdné.
- Pojistka: `kredity_max_na_beh` v `sporty.yaml`. Počet kreditů a zbytek vidíš v logu běhu.
- Bezplatný plán má podle informací, které jsem našel, 500 kreditů měsíčně. To na desítky lig denně
  nestačí. Aktuální ceny a plány si ověř na webu poskytovatele a podle toho nastav, kolik sportů bot bere.

## Kritéria pro jednotlivé sporty (`kriteria/`)

Každý sport z `sporty.yaml` má vlastní soubor `kriteria/<sport>.yaml` (10-33 kritérií, celkem 569):
rozhodčí, rozměry hřiště, počasí, brankář/nadhazovač/QB, únava a kalendář, formát zápasu, patch a mapy v esportu atd.

Každé kritérium má `w` (váha 1-3), `typ` a volitelně `trhy`:
- **veto**: může se změnit těsně před zápasem a zneplatnit cenu (sestava, zranění, počasí, změna soupeře). Gemini je ověřuje.
- **kontext**: strukturální faktor (rozhodčí, délka hřiště, styl). Jde jen do vysvětlení v reportu, nevetuje.

Do dotazu na Gemini jde jen `veto_max_kriterii` (12) nejdůležitějších veto kritérií a `kontext_max_kriterii` (6) kontextových,
seřazených podle váhy. Víc kritérií = víc šumu, víc tokenů a větší riziko vymyšlených odpovědí.
**Váhy jsou můj odhad, ne naměřený vliv.** Měřitelné je jen to, jak si sport vede podle CLV v `bety.csv`.
Chceš-li kritérium přidat nebo upravit, edituj YAML; `python tests/test_kriteria.py` zkontroluje konzistenci.

## Doplňkové trhy a bet buildery (fotbal)

Modul `bot/doplnkove.py` pokrývá celkové **góly, rohy, karty a fauly** a **buildery ze dvou nohou**.
U těchto trhů není ostrá referenční cena (jako Pinnacle u výsledku zápasu), proto pravděpodobnost počítá vlastní model:

1. Týmové míry produkce/obdržených (rohy, fauly...) se **smršťují k průměru ligy** a síla smrštění se **učí z dat**
   (empirický Bayes). Když týmové statistiky nic neříkají, model se přiblíží průměru ligy a nehoní šum.
2. **Rozhodčí** upravuje karty a fauly (také smrštěný faktor). Jméno rozhodčího bot sám nezná: doplň ho do
   `data/rozhodci.json` ve tvaru `{"2026-11-04|Arsenal|Chelsea": "M Oliver"}` (jména jako ve football-data).
3. Počet ~ negativní binomické rozdělení (disperze z reziduí).
4. **Builder** = společné rozdělení více trhů přes Gaussovu kopuli; korelace se odhadne z historie.
5. Výstup: **fér kurz** a **„sázej od"** (fér × (1 + `min_edge` 8 %)), jen když „sázej od" leží v pásmu 1.40-1.90.
   Bot nezná kurzy tvé kanceláře, takže porovnání uděláš ty. Pro builder: `Actions → akce builder` spočítá
   společnou pravděpodobnost a edge proti tvému kurzu (formát v popisu pole `args`).

**Jak poznáš, jestli to něco umí:** `Actions → akce backtest` (arg `E0` nebo `all`) pustí model chronologicky přes
minulý rok a porovná ho s naivním průměrem ligy (logloss). Kladné zlepšení = model něco ví. Kolem nuly = nesázet.
Každý den se navíc loguje předpověď do `data/doplnkove.csv`, po zápase se doplní výsledek a report ukazuje **kalibraci**
(když model říká 65 %, má to vycházet zhruba v 65 %).

**Čeho se to NEDOTÝKÁ:** historie je z football-data.co.uk (hlavní evropské ligy, české ligy tam nejsou), kurzy kanceláří
na tyto trhy bot nemá, takže **CLV a ROI na doplňkových trzích se zatím neměří**. Měří se jen kalibrace pravděpodobností.
Střídání a americký fotbal (yardy hráčů) tu zatím nejsou.

## Co musíš vědět

- **Pinnacle v Odds API je z veřejného webu a může mít zpoždění**, takže „fér kurz" je odhad.
- **České kanceláře (Fortuna, Tipsport...) v Odds API nejsou.** Proto bot dává „sázej od kurzu X" a ty
  ověříš kurz u své kanceláře. Najdeš-li svou kancelář v seznamu klíčů, dej ji do `moje_kancelare`.
- Po vsazení doplň skutečný kurz do sloupce `kurz_vzat` v `data/bety.csv` (stačí upravit v GitHub UI).
  Pak se počítá i reálné ROI.
- Sporty, které Odds API nepokrývá (stolní tenis, esport, šipky, snooker, volejbal, házená, florbal...),
  tu nejsou. Bez sharp reference by tam hranu stejně nic nenašlo.
- GitHub může plánovaný workflow zpozdit a po delší nečinnosti repozitáře naplánované běhy vypnout
  (viz hláška v záložce Actions): případně je jedním klikem znovu zapni.
- Právní stránka: pokud v tom jsou cizí peníze („investoři"), ověř si regulaci. Bot nic nezaručuje.

## Lokální test

```bash
pip install pyyaml google-genai
python tests/test_offline.py        # bez sítě, falešná data
python tests/test_kriteria.py       # kontrola YAML kritérií
python tests/test_doplnkove.py      # model doplňkových trhů (syntetická data)
ODDS_API_KEY=... python -m bot.main sports
```
