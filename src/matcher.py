import re

_SENIORITY_KEYWORDS = {
    "junior": ["junior", "júnior", "jr", "entry", "estágio", "trainee", "intern"],
    "pleno":  ["pleno", "mid", "middle", "ii", " 2 ", "ii "],
    "senior": ["senior", "sênior", "sr", "lead", "staff", "principal", "architect", "especialista"],
}

_ADJACENT = {
    "junior": {"junior", "pleno"},
    "pleno":  {"junior", "pleno", "senior"},
    "senior": {"pleno", "senior"},
}


def score(job: dict, profile: dict) -> tuple[int, dict]:
    """Return (total_score, breakdown) for a job against the profile."""
    breakdown: dict = {}

    skills_score, matched, missing = _score_skills(job, profile)
    seniority_score             = _score_seniority(job, profile)
    location_score              = _score_location(job, profile)
    salary_score                = _score_salary(job, profile)

    total = skills_score + seniority_score + location_score + salary_score

    breakdown["skills_score"]    = skills_score
    breakdown["seniority_score"] = seniority_score
    breakdown["location_score"]  = location_score
    breakdown["salary_score"]    = salary_score
    breakdown["matched_skills"]  = matched
    breakdown["missing_skills"]  = missing

    return total, breakdown


def _score_skills(job: dict, profile: dict) -> tuple[int, list, list]:
    description = (job.get("description") or "").lower()
    title       = (job.get("title") or "").lower()
    text        = description + " " + title

    user_skills = [s.lower() for s in profile.get("skills", [])]
    if not user_skills:
        return 20, [], []

    matched = [s for s in user_skills if re.search(r'\b' + re.escape(s) + r'\b', text)]
    missing = [s for s in user_skills if s not in matched]

    ratio = len(matched) / len(user_skills)
    return round(ratio * 40), matched, missing


def _score_seniority(job: dict, profile: dict) -> int:
    title = (job.get("title") or "").lower()
    target = profile.get("seniority", "pleno")

    detected = _detect_seniority(title)
    if detected is None:
        return 15  # não dá pra saber — neutro

    if detected == target:
        return 30
    if detected in _ADJACENT.get(target, set()):
        return 15
    return 0


def _detect_seniority(title: str) -> str | None:
    for level, keywords in _SENIORITY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            return level
    return None


def _score_location(job: dict, profile: dict) -> int:
    if job.get("remote"):
        return 20

    place = (job.get("location") or "").lower()
    user_city = (profile.get("location") or "").lower()

    if user_city and user_city in place:
        return 20
    if profile.get("accept_remote") and ("remote" in place or "remoto" in place):
        return 20
    return 0


def _score_salary(job: dict, profile: dict) -> int:
    salary = job.get("salary")
    min_s = profile.get("min_salary")
    max_s = profile.get("max_salary")

    if salary is None or min_s is None or max_s is None:
        return 5  # sem informação — neutro

    lo, hi = salary
    if lo <= max_s and hi >= min_s:
        return 10
    return 0
