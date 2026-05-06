"""Playwright-based WordPress admin checks and plugin removal."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from urllib.parse import urljoin

from app.utils.domain_normalization import normalize_domain

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WordPressCheckResult:
    status: str
    message: str = ""
    http_status: int | None = None
    plugin_present: bool = False
    plugin_removed: bool = False
    plugin_was_active: bool | None = None
    newspaper_theme: bool = False
    theme_name: str = ""


class WordPressClient:
    def __init__(
        self,
        timeout_seconds: int = 30,
        headless: bool = True,
        plugin_name: str = "Google Analytics Insertion",
        newspaper_theme_name: str = "Newspaper",
    ):
        self.timeout_ms = timeout_seconds * 1000
        self.headless = headless
        self.plugin_name = plugin_name
        self.newspaper_theme_name = newspaper_theme_name

    def remediate(
        self,
        domain: str,
        username: str,
        password: str,
        dry_run: bool = False,
    ) -> WordPressCheckResult:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed. Run `pip install -r requirements.txt`.") from exc

        base_url = self._base_url(domain)
        login_url = urljoin(base_url, "/wp-login.php")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            page = browser.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                try:
                    response = page.goto(login_url, wait_until="domcontentloaded")
                except PlaywrightTimeoutError:
                    return WordPressCheckResult(status="site_unreachable", message="Timed out loading wp-login.php")
                except Exception as exc:
                    return WordPressCheckResult(status="site_unreachable", message=str(exc))

                http_status = response.status if response else None
                site_error = self._classify_http_status(http_status)
                if site_error:
                    return WordPressCheckResult(status=site_error, http_status=http_status)

                try:
                    page.fill("#user_login", username)
                    page.fill("#user_pass", password)
                    page.click("#wp-submit")
                    page.wait_for_load_state("domcontentloaded")
                except PlaywrightTimeoutError:
                    return WordPressCheckResult(status="login_blocked", http_status=http_status, message="Login timed out")
                except Exception as exc:
                    return WordPressCheckResult(status="login_blocked", http_status=http_status, message=str(exc))

                if self._has_login_error(page):
                    return WordPressCheckResult(status="login_invalid", http_status=http_status, message="Website = login klopt niet")

                admin_response = page.goto(urljoin(base_url, "/wp-admin/"), wait_until="domcontentloaded")
                admin_status = admin_response.status if admin_response else None
                site_error = self._classify_http_status(admin_status)
                if site_error:
                    return WordPressCheckResult(status=site_error, http_status=admin_status)
                if self._looks_like_login_page(page):
                    return WordPressCheckResult(status="login_invalid", http_status=admin_status, message="Website = login klopt niet")

                theme_name, newspaper_theme = self._detect_theme(page, base_url)
                plugin_result = self._remove_plugin(page, base_url, dry_run=dry_run)
                return WordPressCheckResult(
                    status=plugin_result["status"],
                    message=plugin_result.get("message", ""),
                    http_status=admin_status,
                    plugin_present=plugin_result["plugin_present"],
                    plugin_removed=plugin_result["plugin_removed"],
                    plugin_was_active=plugin_result["plugin_was_active"],
                    newspaper_theme=newspaper_theme,
                    theme_name=theme_name,
                )
            finally:
                browser.close()

    def _base_url(self, domain: str) -> str:
        normalized = normalize_domain(domain)
        return f"https://{normalized}/"

    def _classify_http_status(self, status: int | None) -> str | None:
        if status == 404:
            return "site_404"
        if status and status >= 500:
            return "site_500"
        return None

    def _has_login_error(self, page) -> bool:
        try:
            return page.locator("#login_error").count() > 0
        except Exception:
            return False

    def _looks_like_login_page(self, page) -> bool:
        if "wp-login.php" not in page.url:
            return False
        try:
            return page.locator("#user_login").count() > 0 and page.locator("#user_pass").count() > 0
        except Exception:
            return True

    def _detect_theme(self, page, base_url: str) -> tuple[str, bool]:
        try:
            response = page.goto(urljoin(base_url, "/wp-admin/themes.php"), wait_until="domcontentloaded")
            if response and response.status >= 400:
                return "", False
            active_theme = page.locator(".theme.active .theme-name").first
            theme_name = active_theme.inner_text(timeout=3000).strip() if active_theme.count() else ""
            content = page.content()
            newspaper_theme = self.newspaper_theme_name.lower() in theme_name.lower()
            if not newspaper_theme:
                newspaper_theme = f"theme-name\">{self.newspaper_theme_name.lower()}" in content.lower()
            return theme_name, newspaper_theme
        except Exception as exc:
            logger.warning("Could not detect WordPress theme: %s", exc)
            return "", False

    def _remove_plugin(self, page, base_url: str, dry_run: bool) -> dict:
        response = page.goto(urljoin(base_url, "/wp-admin/plugins.php"), wait_until="domcontentloaded")
        if response and response.status >= 500:
            return {
                "status": "site_500",
                "plugin_present": False,
                "plugin_removed": False,
                "plugin_was_active": None,
            }
        if response and response.status == 404:
            return {
                "status": "site_404",
                "plugin_present": False,
                "plugin_removed": False,
                "plugin_was_active": None,
            }

        plugin_row = page.locator("tr").filter(has_text=self.plugin_name).first
        if not plugin_row.count():
            return {
                "status": "plugin_not_found",
                "plugin_present": False,
                "plugin_removed": False,
                "plugin_was_active": None,
            }

        deactivate = self._first_action(plugin_row, ("Deactivate", "Deactiveren"))
        activate = self._first_action(plugin_row, ("Activate", "Activeren"))
        plugin_was_active = deactivate.count() > 0

        if dry_run:
            return {
                "status": "plugin_present_dry_run",
                "plugin_present": True,
                "plugin_removed": False,
                "plugin_was_active": plugin_was_active,
                "message": "Dry-run: plugin would be removed",
            }

        try:
            if plugin_was_active:
                deactivate.click()
                page.wait_for_load_state("domcontentloaded")
                plugin_row = page.locator("tr").filter(has_text=self.plugin_name).first
            elif activate.count() == 0:
                logger.info("Plugin row found but active state could not be determined")

            delete_link = self._first_action(plugin_row, ("Delete", "Verwijderen"))
            if not delete_link.count():
                return {
                    "status": "plugin_remove_failed",
                    "plugin_present": True,
                    "plugin_removed": False,
                    "plugin_was_active": plugin_was_active,
                    "message": "Delete action not available",
                }

            page.once("dialog", lambda dialog: dialog.accept())
            delete_link.click()
            page.wait_for_load_state("domcontentloaded")
            remaining = page.locator("tr").filter(has_text=self.plugin_name).count()
            removed = remaining == 0
            return {
                "status": "plugin_removed" if removed else "plugin_remove_failed",
                "plugin_present": not removed,
                "plugin_removed": removed,
                "plugin_was_active": plugin_was_active,
            }
        except Exception as exc:
            return {
                "status": "plugin_remove_failed",
                "plugin_present": True,
                "plugin_removed": False,
                "plugin_was_active": plugin_was_active,
                "message": str(exc),
            }

    def _first_action(self, row, labels: tuple[str, ...]):
        links = row.locator("a")
        for label in labels:
            candidate = links.filter(has_text=label).first
            if candidate.count() > 0:
                return candidate
        return links.filter(has_text=labels[0]).first
