"""Salário (com conversão para real) e tipo de contrato (CLT/PJ) das vagas."""
import json
import logging
import re
import urllib.request

logger = logging.getLogger(__name__)

# ── Salário ─────────────────────────────────────────────────────────────────

_CURRENCIES = {
    "R$": "BRL", "BRL": "BRL", "REAIS": "BRL",
    "US$": "USD", "U$": "USD", "USD": "USD", "$": "USD", "DÓLARES": "USD", "DOLARES": "USD",
    "€": "EUR", "EUR": "EUR", "EUROS": "EUR",
    "£": "GBP", "GBP": "GBP",
}
_SYMBOL = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£"}

_CUR = r"(R\$|US\$|U\$|USD|BRL|EUR|GBP|€|£|\$)"
_NUM = r"(\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*([kK]\b|mil\b)?"
_SEP = r"\s*(?:-|–|—|a|até|to)\s*"
_SUFFIX_CUR = r"\s*(BRL|reais|USD|d[óo]lares|EUR|euros|GBP)"

_RANGE_PREFIX = re.compile(_CUR + r"\s*" + _NUM + _SEP + r"(?:" + _CUR + r"\s*)?" + _NUM, re.I)
_RANGE_SUFFIX = re.compile(_NUM + _SEP + _NUM + _SUFFIX_CUR, re.I)
_SINGLE_PREFIX = re.compile(_CUR + r"\s*" + _NUM, re.I)

_PERIODS = (
    ("hora", r"/\s*h(?:r|our|ora)?\b|per hour|por hora|hourly|an hour"),
    ("mês",  r"/\s*m[eê]s|por m[eê]s|mensa|per month|/\s*mo(?:nth)?\b|monthly|a month"),
    ("ano",  r"/\s*(?:ano|yr|year)\b|por ano|anua|per year|per annum|annual|yearly|a year"),
)


def _parse_amount(num: str, suffix: str | None) -> float:
    num = num.replace(" ", "")
    if "." in num and "," in num:
        dec = "." if num.rfind(".") > num.rfind(",") else ","
        num = num.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "," in num or "." in num:
        sep = "," if "," in num else "."
        tail = num.rsplit(sep, 1)[1]
        num = num.replace(sep, "") if len(tail) == 3 else num.replace(sep, ".")
    value = float(num)
    if suffix and suffix.lower() in ("k", "mil"):
        value *= 1000
    return value


def _period(text_after: str) -> str | None:
    window = text_after[:60].lower()
    for name, pattern in _PERIODS:
        if re.search(pattern, window):
            return name
    return None


def extract_salary(text: str) -> dict | None:
    """Acha a faixa salarial no texto: {lo, hi, currency, period}."""
    if not text:
        return None
    for regex, kind in ((_RANGE_PREFIX, "prefix"), (_RANGE_SUFFIX, "suffix"), (_SINGLE_PREFIX, "single")):
        for m in regex.finditer(text):
            g = m.groups()
            if kind == "prefix":
                cur, lo, hi = g[0], _parse_amount(g[1], g[2]), _parse_amount(g[4], g[5])
            elif kind == "suffix":
                cur, lo, hi = g[4], _parse_amount(g[0], g[1]), _parse_amount(g[2], g[3])
            else:
                cur, lo = g[0], _parse_amount(g[1], g[2])
                hi = lo
            currency = _CURRENCIES.get(cur.upper())
            period = _period(text[m.end():])
            # descarta números que não parecem salário (ex.: "R$ 5 de VR", "$1B de receita")
            if not currency or lo <= 0 or hi < lo or hi > 5_000_000:
                continue
            if lo < 100 and period != "hora":
                continue
            return {"lo": lo, "hi": hi, "currency": currency, "period": period}
    return None


_rates: dict[str, float] = {"BRL": 1.0}


def _rate_to_brl(currency: str) -> float | None:
    """Cotação atual (1 unidade da moeda em reais), buscada uma vez por execução."""
    if currency in _rates:
        return _rates[currency]
    sources = (
        (f"https://api.frankfurter.dev/v1/latest?base={currency}&symbols=BRL",
         lambda d: d["rates"]["BRL"]),
        (f"https://open.er-api.com/v6/latest/{currency}", lambda d: d["rates"]["BRL"]),
    )
    for url, pick in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "linkedinbot"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                _rates[currency] = float(pick(json.load(resp)))
                return _rates[currency]
        except Exception as exc:
            logger.warning("Cotação %s→BRL indisponível em %s: %s", currency, url, exc)
    return None


def monthly_brl(salary: dict | None) -> tuple[float, float] | None:
    """Faixa convertida para reais por mês (usada no score de salário)."""
    if not salary:
        return None
    rate = _rate_to_brl(salary["currency"])
    if rate is None:
        return None
    factor = {"hora": 160, "ano": 1 / 12}.get(salary["period"], 1)
    return salary["lo"] * rate * factor, salary["hi"] * rate * factor


def _money(value: float, symbol: str) -> str:
    return f"{symbol} " + f"{value:,.0f}".replace(",", ".")


def format_salary(salary: dict) -> str:
    """Ex.: 'R$ 5.000 – 7.000/mês', 'US$ 4.000 – 5.000/mês (≈ R$ 21.600 – 27.000/mês)'
    ou 'US$ 60.000 – 80.000/ano (≈ R$ 27.000 – 36.000/mês)'."""
    per = f"/{salary['period']}" if salary.get("period") else ""
    sym = _SYMBOL[salary["currency"]]

    def rng(lo: float, hi: float, s: str) -> str:
        if round(lo) == round(hi):
            return _money(lo, s) + per
        return f"{_money(lo, s)} – {f'{hi:,.0f}'.replace(',', '.')}{per}"

    text = rng(salary["lo"], salary["hi"], sym)
    if salary["currency"] != "BRL" or salary.get("period") == "ano":
        brl = monthly_brl(salary) if salary.get("period") == "ano" else None
        if brl:  # anual → mostra o equivalente mensal em reais
            lo, hi = brl
            conv = (_money(lo, "R$") if round(lo) == round(hi)
                    else f"{_money(lo, 'R$')} – {f'{hi:,.0f}'.replace(',', '.')}") + "/mês"
            text += f" (≈ {conv})"
        elif salary["currency"] != "BRL" and (rate := _rate_to_brl(salary["currency"])):
            text += f" (≈ {rng(salary['lo'] * rate, salary['hi'] * rate, 'R$')})"
    return text


# ── Tipo de contrato ────────────────────────────────────────────────────────

_CONTRACTS = (
    ("CLT",       r"\bclt\b|carteira assinada|regime efetivo"),
    ("PJ",        r"\bpj\b|pessoa jur[ií]dica|\bcontractor\b|independent contractor|\bb2b\b"),
    ("Freelance", r"\bfreelanc\w*|\bfreela\b"),
    ("Estágio",   r"\best[áa]gio\b|\binternship\b"),
    ("Cooperado", r"\bcooperad[oa]\b"),
)
_EMPLOYMENT_TYPES = {
    "contract": "PJ", "contrato": "PJ",
    "temporary": "Temporário", "temporário": "Temporário",
    "internship": "Estágio", "estágio": "Estágio",
}


def detect_contract(text: str, employment_type: str = "") -> str | None:
    """CLT, PJ, Freelance… a partir da descrição e do 'tipo de emprego' do LinkedIn."""
    found = [name for name, pattern in _CONTRACTS if re.search(pattern, text or "", re.I)]
    if "CLT" in found and "PJ" in found:
        return "CLT ou PJ"
    if found:
        return found[0]
    return _EMPLOYMENT_TYPES.get((employment_type or "").strip().lower())
