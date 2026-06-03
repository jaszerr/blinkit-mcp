from playwright.async_api import Page
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.order.blinkit_order import BlinkitOrder


class BaseService:
    def __init__(self, page: Page, manager: Optional["BlinkitOrder"] = None):
        self.page = page
        self.manager = manager

    async def _is_store_closed(self):
        """Checks if the store is closed or unavailable."""
        if await self.page.is_visible("text=Store is closed"):
            print("CRITICAL: Store is closed.")
            return True
        return False

    async def _safe_click(self, locator, description="element", timeout=10000):
        """Click an element with fallback strategies: scroll into view, force click, JS click.

        A plain Playwright click waits for actionability and can hang for the
        full timeout when a sticky/overlapping element covers the target (the
        checkout "Proceed" CTA is a common offender). Falling back to a forced
        click and then a JS click clears those cases. Returns True if any
        strategy clicked the element.
        """
        try:
            # First, scroll the element into view
            await locator.scroll_into_view_if_needed(timeout=5000)
            await self.page.wait_for_timeout(300)
        except Exception:
            pass

        # Attempt 1: Normal click
        try:
            await locator.click(timeout=timeout)
            return True
        except Exception as e:
            print(f"Normal click failed on {description}: {e}")

        # Attempt 2: Force click (bypasses actionability checks)
        try:
            await locator.click(force=True, timeout=5000)
            print(f"Force click succeeded on {description}.")
            return True
        except Exception as e:
            print(f"Force click failed on {description}: {e}")

        # Attempt 3: JavaScript click (last resort)
        try:
            await locator.evaluate("el => el.click()")
            print(f"JS click succeeded on {description}.")
            return True
        except Exception as e:
            print(f"JS click failed on {description}: {e}")

        return False
