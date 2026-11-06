"""Test ručních kurzů (data/moje_kurzy.csv). Bez sítě."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import config, mojekurzy  # noqa: E402


def test_aplikuj():
    tmp = Path(tempfile.mkdtemp()); config.DATA = tmp
    (tmp / "moje_kurzy.csv").write_text(
        "home,away,trh,vyber,linie,strana,kurz,kancelar\n"
        "Man Utd,Arsenal FC,h2h,Manchester United,,,2,60,tipsport\n"          # špatný řádek (čárka v kurzu) se přeskočí
        "Man Utd,Arsenal FC,h2h,Manchester United,,,2.60,tipsport\n"
        "Man Utd,Arsenal FC,fauly,,22.5,over,1.85,tipsport\n", encoding="utf-8")
    cfg = {"nastaveni": {"min_edge": 0.03}, "doplnkove": {"min_edge": 0.08}}
    pick = {"zapas": "Manchester United vs Arsenal", "vyber": "Manchester United",
            "fair_p": 0.42, "min_kurz": 2.45, "moje_kurz": "", "edge": 0.0}
    dopl = [{"home_fd": "Man United", "away_fd": "Arsenal",
             "linie": [{"var": "fauly", "linie": 22.5, "strana": "over", "p": 0.60}]}]
    n = mojekurzy.aplikuj([pick], dopl, cfg)
    assert n == 2, n
    assert pick["moje_kurz"] == 2.6 and abs(pick["edge"] - (2.6 * 0.42 - 1)) < 1e-4 and "vyplatí" in pick["moje_info"]
    l = dopl[0]["linie"][0]
    assert l["moje_kurz"] == 1.85 and l["moje_info"].endswith("✅")      # 1.85*0.60-1 = +11 %
    assert mojekurzy.aplikuj([{"zapas": "A vs B", "vyber": "A", "fair_p": .5, "min_kurz": 2.1}], [], cfg) == 0


if __name__ == "__main__":
    test_aplikuj(); print("✅ test_aplikuj")
