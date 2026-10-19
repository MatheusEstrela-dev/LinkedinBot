import logging
import re

from linkedin_jobs_scraper import LinkedinScraper
from linkedin_jobs_scraper.events import EventData, Events
from linkedin_jobs_scraper.exceptions import InvalidCookieException
from linkedin_jobs_scraper.filters import (
    ExperienceLevelFilters,
    OnSiteOrRemoteFilters,
    RelevanceFilters,
    TimeFilters,
)
from linkedin_jobs_scraper.query import Query, QueryFilters, QueryOptions

logger = logging.getLogger(__name__)

_SENIORITY_FILTER = {
    "junior": [ExperienceLevelFilters.ENTRY_LEVEL, ExperienceLevelFilters.INTERNSHIP],
    "pleno":  [ExperienceLevelFilters.MID_SENIOR],
    "senior": [ExperienceLevelFilters.MID_SENIOR, ExperienceLevelFilters.DIRECTOR],
}


def _build_scraper(on_data, on_error) -> LinkedinScraper:
    scraper = LinkedinScraper(
        chrome_executable_path=None,
        headless=True,
        max_workers=1,
        slow_mo=1.5,
        page_load_timeout=40,
    )
    scraper.on(Events.DATA,  on_data)
    scraper.on(Events.ERROR, on_error)
    return scraper


def fetch_jobs(profile: dict) -> list[dict]:
    from . import auth as _auth

    results: list[dict] = []

    def on_data(data: EventData):
        results.append({
            "id":          data.job_id,
            "title":       data.title,
            "company":     data.company,
            "location":    data.place,
            "description": data.description,
            "link":        data.link,
            "remote":      _is_remote(data.place, data.description),
        })
        _add_compensation(results[-1])

    def on_error(err):
        logger.error("Scraper error: %s", err)

    seniority = profile.get("seniority", "pleno")
    exp_filters = _SENIORITY_FILTER.get(seniority, [ExperienceLevelFilters.MID_SENIOR])
    remote_filters = (
        [OnSiteOrRemoteFilters.REMOTE, OnSiteOrRemoteFilters.HYBRID]
        if profile.get("accept_remote") else []
    )
    locations = ["Brazil"]
    if not profile.get("accept_remote") and profile.get("location"):
        locations = [profile["location"]]

    # Scraper com navegador (login via cookie). Desligado por padrão: o LinkedIn
    # derruba o cookie quando usado pelo GitHub Actions e a página logada não
    # retorna vagas para a biblioteca. A API pública abaixo cobre a busca.
    if profile.get("browser_scraper"):
        for role in profile.get("target_roles", []):
            query = Query(
                query=role,
                options=QueryOptions(
                    locations=locations,
                    apply_link=False,
                    limit=25,
                    filters=QueryFilters(
                        relevance=RelevanceFilters.RECENT,
                        time=TimeFilters.WEEK,
                        experience=exp_filters,
                        on_site_or_remote=remote_filters or None,
                    ),
                ),
            )
            scraper = _build_scraper(on_data, on_error)
            try:
                scraper.run(query)
            except InvalidCookieException:
                logger.warning("Cookie expirado — tentando renovar automaticamente...")
                new_cookie = _auth.refresh_cookie()
                if new_cookie:
                    scraper = _build_scraper(on_data, on_error)
                    try:
                        scraper.run(query)
                    except Exception as exc:
                        logger.error("Falhou mesmo após renovação: %s", exc)
                        break
                else:
                    logger.warning("Renovação falhou — retornando %d vagas coletadas", len(results))
                    from . import notifier
                    notifier.send_alert(
                        "o cookie do LinkedIn expirou e o login automático falhou, "
                        "então nenhuma vaga está sendo buscada. Atualize o secret "
                        "LI_AT_COOKIE no GitHub (Settings → Secrets → Actions)."
                    )
                    break
            except Exception as exc:
                logger.error("Erro ao buscar '%s': %s", role, exc)
                break

    from . import guest_scraper
    guest_scraper.start_budget(profile.get("search_budget_minutes", 15) * 60)

    if not results:
        params = {"f_TPR": "r604800", "f_E": ",".join(f.value for f in exp_filters)}
        if remote_filters:
            params["f_WT"] = ",".join(f.value for f in remote_filters)
        for role in profile.get("target_roles", []):
            for job in guest_scraper.search(role, locations[0], params):
                _add_compensation(job)
                job["remote"] = _is_remote(job["location"], job["description"])
                results.append(job)

    intl = profile.get("international") or {}
    if intl.get("enabled"):
        results.extend(_fetch_international(intl, profile, exp_filters, {j["id"] for j in results}))

    logger.info("Scraper encontrou %d vagas no total", len(results))
    return results


def _fetch_international(intl: dict, profile: dict, exp_filters, seen_ids: set) -> list[dict]:
    """Vagas remotas fora do Brasil, via API pública (termos em inglês)."""
    from . import guest_scraper

    params = {
        "f_TPR": "r604800",
        "f_E": ",".join(f.value for f in exp_filters),
        "f_WT": OnSiteOrRemoteFilters.REMOTE.value,
    }
    found: list[dict] = []
    for role in intl.get("roles") or profile.get("target_roles", []):
        for location in intl.get("locations", ["Worldwide"]):
            for job in guest_scraper.search(role, location, params, limit=intl.get("limit", 15)):
                if job["id"] in seen_ids:
                    continue
                seen_ids.add(job["id"])
                # A API às vezes ignora o filtro de remoto: descarta híbridas/presenciais.
                text = f"{job['title']} {job['location']} {job['description']}".lower()
                if "hybrid" in text or "híbrid" in text or not _is_remote(text, ""):
                    continue
                _add_compensation(job)
                job["language"] = _detect_language(f"{job['title']} {job['description']}")
                job["remote"] = True
                job["international"] = True
                found.append(job)
    logger.info("Busca internacional: %d vagas", len(found))
    return found


def _add_compensation(job: dict) -> None:
    """Preenche salário (moeda original + faixa mensal em reais) e tipo de contrato."""
    from . import compensation
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    job["salary"] = (compensation.extract_salary(job.get("salary_text", ""))
                     or compensation.extract_salary(text))
    job["salary_brl"] = compensation.monthly_brl(job["salary"])
    job["contract"] = compensation.detect_contract(text, job.get("employment_type", ""))


_LANG_WORDS = {
    "Inglês":    {"the", "and", "with", "you", "we", "our", "will", "experience", "team", "for"},
    "Espanhol":  {"el", "los", "las", "con", "para", "una", "experiencia", "trabajo", "del", "y"},
    "Português": {"os", "com", "para", "uma", "experiência", "você", "nossa", "trabalho", "do", "e"},
    "Francês":   {"le", "les", "des", "avec", "pour", "une", "vous", "nous", "et", "expérience"},
    "Alemão":    {"der", "die", "und", "mit", "für", "wir", "sie", "ein", "erfahrung", "ist"},
    "Italiano":  {"il", "gli", "con", "per", "una", "esperienza", "lavoro", "della", "che", "siamo"},
}


def _detect_language(text: str) -> str:
    """Idioma provável da vaga, contando palavras comuns de cada língua."""
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    counts = {lang: sum(w in vocab for w in words) for lang, vocab in _LANG_WORDS.items()}
    lang, hits = max(counts.items(), key=lambda kv: kv[1])
    return lang if hits >= 3 else "Não identificado"


def _is_remote(place: str, description: str) -> bool:
    keywords = ("remote", "remoto", "home office", "anywhere", "teletrabajo", "télétravail")
    combined = (place + " " + description).lower()
    return any(kw in combined for kw in keywords)
