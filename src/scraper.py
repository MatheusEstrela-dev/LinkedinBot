import logging

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
            "salary":      _extract_salary(data.description),
            "remote":      _is_remote(data.place, data.description),
        })

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
                break
        except Exception as exc:
            logger.error("Erro ao buscar '%s': %s", role, exc)
            break

    logger.info("Scraper encontrou %d vagas no total", len(results))
    return results


def _extract_salary(description: str) -> tuple[int, int] | None:
    import re
    patterns = [
        r"R\$\s*([\d\.]+)\s*[-–a]\s*R\$\s*([\d\.]+)",
        r"([\d\.]+)\s*[-–]\s*([\d\.]+)\s*(?:BRL|reais)",
    ]
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            lo = int(match.group(1).replace(".", ""))
            hi = int(match.group(2).replace(".", ""))
            return (lo, hi)
    return None


def _is_remote(place: str, description: str) -> bool:
    keywords = ("remote", "remoto", "home office", "anywhere")
    combined = (place + " " + description).lower()
    return any(kw in combined for kw in keywords)
