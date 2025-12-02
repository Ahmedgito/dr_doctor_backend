from __future__ import annotations

import time
from contextlib import AbstractContextManager
from typing import Optional, Callable

from loguru import logger
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError


class BaseScraper(AbstractContextManager):
    """Base scraper that manages Playwright browser and provides helper methods.

    Usage:
        with BaseScraper() as scraper:
            scraper.load_page("https://example.com")
            html = scraper.get_html()
    """

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 15000,
        max_retries: int = 3,
        wait_between_retries: float = 2.0,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.wait_between_retries = wait_between_retries

        self._playwright = None
        self.browser = None
        self.page: Optional[Page] = None

    # --- context manager lifecycle -------------------------------------------------

    def __enter__(self) -> "BaseScraper":
        logger.debug("Starting Playwright...")
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        logger.info("Playwright browser started (headless={})", self.headless)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        logger.debug("Shutting down Playwright...")
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error while closing Playwright resources: {}", exc)

    # --- core navigation helpers ---------------------------------------------------

    def _retry(self, func: Callable[[], None], action_name: str) -> None:
        """Generic retry wrapper for Playwright actions."""

        for attempt in range(1, self.max_retries + 1):
            try:
                func()
                return
            except PlaywrightTimeoutError as exc:
                logger.warning(
                    "Timeout during action '{}' (attempt {}/{}): {}",
                    action_name,
                    attempt,
                    self.max_retries,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Error during action '{}' (attempt {}/{}): {}",
                    action_name,
                    attempt,
                    self.max_retries,
                    exc,
                )

            if attempt < self.max_retries:
                time.sleep(self.wait_between_retries)

        raise RuntimeError(f"Action '{action_name}' failed after {self.max_retries} attempts")

    def load_page(self, url: str) -> None:
        """Navigate to a URL with retry logic."""

        if not self.page:
            raise RuntimeError("Playwright page is not initialized. Use the scraper as a context manager.")

        logger.info("Loading page: {}", url)

        def _go() -> None:
            assert self.page is not None
            self.page.goto(url, wait_until="networkidle")

        self._retry(_go, f"load_page: {url}")

    def wait_for(self, selector: str, timeout_ms: Optional[int] = None) -> None:
        """Wait for a selector to appear on the page."""

        if not self.page:
            raise RuntimeError("Playwright page is not initialized. Use the scraper as a context manager.")

        timeout = timeout_ms or self.timeout_ms
        logger.debug("Waiting for selector '{}' (timeout={} ms)", selector, timeout)

        def _wait() -> None:
            assert self.page is not None
            self.page.wait_for_selector(selector, timeout=timeout)

        self._retry(_wait, f"wait_for: {selector}")

    def get_html(self) -> str:
        """Return the current page HTML."""

        if not self.page:
            raise RuntimeError("Playwright page is not initialized. Use the scraper as a context manager.")

        logger.debug("Getting page HTML")
        return self.page.content()

    def extract_text(self, selector: str) -> Optional[str]:
        """Safely get inner text for a CSS selector on the current page."""

        if not self.page:
            raise RuntimeError("Playwright page is not initialized. Use the scraper as a context manager.")

        try:
            element = self.page.query_selector(selector)
            if not element:
                return None
            return element.inner_text().strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to extract text for selector '{}': {}", selector, exc)
            return None
