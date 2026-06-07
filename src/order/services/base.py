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
        """Click an element with fallback strategies: scroll into view, force
        click, trusted mouse click at center, JS click.

        A plain Playwright click waits for actionability and can hang for the
        full timeout when the target's subtree re-renders continuously (the
        header cart button mutates with the delivery ETA, so it is never
        "stable"), and a forced click can still die retrying against a node
        that detaches mid-action. The coordinate mouse click is immune to
        both: it fires a trusted event at the element's center that hits the
        topmost element there and bubbles like a human click. That also makes
        it reach handlers a JS el.click() misses — el.click() dispatches on
        the matched wrapper only and never bubbles DOWN to the inner child
        that owns the React handler (why the cart drawer silently failed to
        open). Returns True if any strategy clicked the element.
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

        # Money-path guard shared by the two trusted coordinate strategies
        # below (forced click and raw mouse click). Both dispatch real clicks
        # at coordinates: force=True skips Playwright's "receives events"
        # check and a raw mouse click never had one, so an overlay covering
        # the target would swallow the click -- on the checkout/payment
        # screens possibly on a paying control. Only proceed when the topmost
        # element at the target's center is the target itself or one of its
        # descendants. Iframe content and off-viewport targets fail the probe
        # (coordinate mismatch / null) and fall through to the JS click.
        cx = cy = None
        on_target = False
        try:
            box = await locator.bounding_box()
            if box and box["width"] > 0 and box["height"] > 0:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                on_target = await locator.evaluate(
                    """(el, point) => {
                        const hit = document.elementFromPoint(point.x, point.y);
                        return !!hit && (hit === el || el.contains(hit));
                    }""",
                    {"x": cx, "y": cy},
                )
        except Exception as e:
            print(f"Hit-target probe failed on {description}: {e}")

        if on_target:
            # Attempt 2: Force click (bypasses actionability checks)
            try:
                await locator.click(force=True, timeout=5000)
                print(f"Force click succeeded on {description}.")
                return True
            except Exception as e:
                print(f"Force click failed on {description}: {e}")

            # Attempt 3: Trusted mouse click at the element's center
            try:
                await self.page.mouse.click(cx, cy)
                print(f"Mouse click succeeded on {description}.")
                return True
            except Exception as e:
                print(f"Mouse click failed on {description}: {e}")
        else:
            print(
                f"Skipping coordinate clicks on {description}: center is covered by another element."
            )

        # Attempt 4: JavaScript click (last resort)
        try:
            await locator.evaluate("el => el.click()")
            print(f"JS click succeeded on {description}.")
            return True
        except Exception as e:
            print(f"JS click failed on {description}: {e}")

        return False
