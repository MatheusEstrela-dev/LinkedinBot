import logging
import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from linkedin_jobs_scraper.config import Config
from linkedin_jobs_scraper.utils.chrome_driver import build_driver

logger = logging.getLogger(__name__)


def refresh_cookie() -> str | None:
    email = os.environ.get("LI_EMAIL")
    password = os.environ.get("LI_PASSWORD")

    if not email or not password:
        logger.warning("LI_EMAIL/LI_PASSWORD não configurados — renovação automática indisponível")
        return None

    logger.info("Renovando cookie do LinkedIn via login automático...")
    driver = build_driver(headless=True, timeout=30)

    try:
        driver.get("https://www.linkedin.com/login")

        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.ID, "username")))

        driver.find_element(By.ID, "username").send_keys(email)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

        time.sleep(6)

        if any(kw in driver.current_url for kw in ("challenge", "checkpoint", "captcha")):
            logger.error("LinkedIn pediu verificação manual (captcha/2FA) — não foi possível renovar")
            return None

        cookies = driver.get_cookies()
        li_at = next((c["value"] for c in cookies if c["name"] == "li_at"), None)

        if li_at:
            # Atualiza para o scraper pegar na próxima instância
            os.environ["LI_AT_COOKIE"] = li_at
            Config.LI_AT_COOKIE = li_at
            logger.info("Cookie renovado com sucesso")
        else:
            logger.error("Cookie li_at não encontrado após login")

        return li_at

    except Exception as exc:
        logger.error("Erro durante login automático: %s", exc)
        return None
    finally:
        try:
            driver.quit()
        except Exception:
            pass
