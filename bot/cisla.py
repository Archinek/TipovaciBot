"""České formátování čísel pro report: tisíce oddělené nezlomitelnou mezerou, desetinná čárka."""
NBSP = " "


def tis(n):
    """Celé číslo po tisících: 40425 -> '40 425'. None -> '–'."""
    if n is None: return "–"
    return f"{int(round(n)):,}".replace(",", NBSP)


def cz(x, d=2):
    """Desetinné číslo po tisících s čárkou: 6797.77 -> '6 797,77'."""
    if x is None: return "–"
    return f"{x:,.{d}f}".replace(",", NBSP).replace(".", ",")


def kc(x, d=0):
    return f"{cz(x, d)}{NBSP}Kč"
