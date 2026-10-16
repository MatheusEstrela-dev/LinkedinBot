"""Busca vagas pela API pública (guest) do LinkedIn — sem login e sem navegador.

Usado como plano B quando o linkedin-jobs-scraper não encontra nada
(ex.: LinkedIn mudou o layout da página autenticada).
"""
import html
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
_PAGE_SIZE = 10

# Prazo global da busca: passado esse ponto, o bot para de pedir páginas e
# descrições e segue com o que já coletou, para nunca estourar o timeout do
# GitHub Actions sem ter enviado nenhuma vaga.
_deadline: float | None = None


def start_budget(seconds: float) -> None:
    global _deadline
    _deadline = time.monotonic() + seconds


def _time_left() -> float:
    return float("inf") if _deadline is None else _deadline - time.monotonic()


def _get(url: str, retries: int = 3) -> str:
    """GET com nova tentativa quando o LinkedIn limita (HTTP 429)."""
    req = urllib.request.Request(url, headers=_HEADERS)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == retries:
                raise
            wait = 5 * (attempt + 1) ** 2  # 5s, 20s, 45s
            if wait >= _time_left():
                raise
            logger.info("LinkedIn limitou (429) — aguardando %ds", wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _text(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.S)
    return _text(match.group(1)) if match else ""


def _parse_cards(page: str) -> list[dict]:
    jobs = []
    for card in page.split("<li")[1:]:
        job_id = re.search(r"jobPosting:(\d+)", card)
        if not job_id:
            continue
        link = re.search(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', card) \
            or re.search(r'href="([^"]*/jobs/view/[^"]+)"', card)
        jobs.append({
            "id":       job_id.group(1),
            "title":    _first(r'class="base-search-card__title[^"]*"[^>]*>(.*?)</h3>', card),
            "company":  _first(r'class="base-search-card__subtitle[^"]*"[^>]*>(.*?)</h4>', card),
            "location": _first(r'class="job-search-card__location[^"]*"[^>]*>(.*?)</span>', card),
            "link":     html.unescape(link.group(1)).split("?")[0] if link else
                        f"https://www.linkedin.com/jobs/view/{job_id.group(1)}",
        })
    return jobs


def _fetch_description(job_id: str) -> str:
    if _time_left() <= 0:
        return ""
    try:
        page = _get(_DETAIL_URL.format(job_id=job_id), retries=1)
    except Exception as exc:
        logger.warning("Sem descrição para vaga %s: %s", job_id, exc)
        return ""
    return _first(r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', page)


def search(role: str, location: str, params: dict, limit: int = 25) -> list[dict]:
    """Retorna vagas no formato {id, title, company, location, link, description}."""
    found: list[dict] = []
    if _time_left() <= 0:
        logger.warning("[guest] prazo da busca esgotado — pulando '%s' (%s)", role, location)
        return found
    for start in range(0, limit, _PAGE_SIZE):
        query = {"keywords": role, "location": location, "sortBy": "DD",
                 "start": start, **params}
        url = f"{_SEARCH_URL}?{urllib.parse.urlencode(query)}"
        try:
            cards = _parse_cards(_get(url))
        except Exception as exc:
            logger.error("Guest API falhou para '%s': %s", role, exc)
            break
        if not cards:
            break
        found.extend(cards)
        time.sleep(2)

    found = found[:limit]
    for job in found:
        job["description"] = _fetch_description(job["id"])
        time.sleep(1.5)

    logger.info("[guest] '%s': %d vagas", role, len(found))
    return found
