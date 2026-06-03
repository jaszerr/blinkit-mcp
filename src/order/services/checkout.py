from .base import BaseService


class CheckoutService(BaseService):
    async def place_order(self):
        """Proceeds to checkout."""

        if await self._is_store_closed():
            return "CRITICAL: Store is closed."

        try:
            # The cart checkout button is the CheckoutStrip CTA ("Proceed To
            # Pay"). Target its focusable container (tabindex=0) specifically,
            # instead of the old broad `button, div` "Proceed" filter with
            # `.last`, which matched several nested containers and could click
            # the wrong element / fire at the wrong checkout stage.
            proceed_btn = (
                self.page.locator("div[class*='CheckoutStrip__AmountContainer']")
                .filter(has_text="Proceed")
                .first
            )

            # If Proceed not visible, open the cart. Try the cart button first,
            # then fall back to navigating straight to the full /cart page,
            # which reliably renders the CheckoutStrip CTA from any page state.
            if not await proceed_btn.is_visible():
                print("Proceed button not visible. Attempting to open Cart drawer...")
                cart_btn = self.page.locator(
                    "div[class*='CartButton__Button'], div[class*='CartButton__Container']"
                )
                if await cart_btn.count() > 0:
                    await self._safe_click(cart_btn.first, "My Cart button")
                    await self.page.wait_for_timeout(2000)
                else:
                    print("Could not find 'My Cart' button.")

                if not await proceed_btn.is_visible():
                    print("Opening full cart page directly...")
                    try:
                        await self.page.goto(
                            "https://blinkit.com/cart", wait_until="domcontentloaded"
                        )
                        await self.page.wait_for_timeout(2000)
                    except Exception as e:
                        print(f"Failed to open /cart page: {e}")

            # Click Proceed with scroll/force/JS fallbacks. A plain click hangs
            # for the full timeout when a sticky element overlaps the CTA, which
            # is the "button found but click never goes through" stall.
            if await proceed_btn.is_visible():
                clicked = await self._safe_click(proceed_btn, "Proceed To Pay")
                if clicked:
                    print(
                        "Cart checkout successfully.\nYou can select the payment method and proceed to pay."
                    )
                    await self.page.wait_for_timeout(3000)
                else:
                    return "ERROR: Found the Proceed button but could not click it."
            else:
                print(
                    "Proceed button not visible. Cart might be empty or Store Unavailable."
                )

        except Exception as e:
            print(f"ERROR: Failed to place order: {e}")

    async def _is_tile_disabled(self, panel, button=None):
        """Best-effort check for whether a payment tile is non-selectable.

        The widget can mark a method unavailable in several ways: a disabled /
        aria-disabled attribute, greyed-out styling (pointer-events: none or low
        opacity), a hidden tile, or an 'unavailable' label. The old behaviour
        only checked the attribute, so a class/visibility-disabled tile got
        clicked anyway. Probe all of them instead.
        """
        try:
            if not await panel.is_visible():
                return True
            for el in (panel, button):
                if el is None or await el.count() == 0:
                    continue
                if await el.first.get_attribute("disabled") is not None:
                    return True
                if await el.first.get_attribute("aria-disabled") == "true":
                    return True
            styled_off = await panel.first.evaluate(
                """el => {
                    const s = getComputedStyle(el);
                    return s.pointerEvents === 'none' || parseFloat(s.opacity) < 0.4;
                }"""
            )
            if styled_off:
                return True
            txt = (await panel.first.inner_text()).lower()
            if "unavailable" in txt or "not available" in txt:
                return True
        except Exception:
            # If the probe itself fails, don't falsely claim the tile is disabled.
            return False
        return False

    async def select_payment_method(self):
        """Checks for Cash availability, selects it if available, else falls back to UPI QR."""
        print("Selecting payment method (Cash or UPI QR)...")
        try:
            iframe_element = await self.page.wait_for_selector(
                "#payment_widget", timeout=30000
            )
            if not iframe_element:
                print("Payment widget iframe not found.")
                return "ERROR: Payment widget not found."

            frame = await iframe_element.content_frame()
            if not frame:
                return "ERROR: Payment widget frame content not found."

            # Wait for the payment options to render. networkidle can hang
            # forever on a widget that keeps polling / sending analytics, so
            # bound the wait to the tiles we actually need and fall through on
            # timeout instead of blocking the whole tool call.
            try:
                await frame.locator(
                    "div[title='Cash'], div[title='UPI']"
                ).first.wait_for(state="visible", timeout=15000)
            except Exception:
                print("Payment options did not render within 15s; proceeding anyway.")

            # Check Cash
            cash_panel = frame.locator("div[title='Cash']")
            if await cash_panel.count() > 0:
                cash_button = cash_panel.locator("div[role='button']")
                if not await self._is_tile_disabled(cash_panel, cash_button):
                    print("Cash is available. Selecting Cash on Delivery...")
                    if await cash_button.count() > 0:
                        await cash_button.first.click()
                    else:
                        await cash_panel.first.click()
                    return "Selected Cash on Delivery. Call pay_now to finalize."
                else:
                    print("Cash is unavailable or disabled.")
            else:
                print("Cash option not found.")

            # If Cash is disabled or doesn't exist, try UPI -> Generate QR
            print("Selecting UPI and generating QR code...")
            upi_panel = frame.locator("div[title='UPI']")
            if await upi_panel.count() > 0:
                upi_button = upi_panel.locator("div[role='button']")
                if await upi_button.count() > 0:
                    # Check if already open
                    is_open = (
                        await upi_button.first.get_attribute("aria-expanded") == "true"
                    )
                    if not is_open:
                        await upi_button.first.click()
                        print("Clicked UPI.")
                else:
                    await upi_panel.first.click()

                await self.page.wait_for_timeout(1000)

                # Click Generate QR
                generate_qr_btn = frame.locator("button:has-text('Generate QR')")
                if await generate_qr_btn.count() > 0:
                    await generate_qr_btn.first.click()
                    print("Generated QR code. Please show the QR code to the customer.")
                    await self.page.wait_for_timeout(2000)  # Wait for QR to load

                    try:
                        qr_img_locator = frame.locator(
                            "div[class*='QrImageWrapper'] img"
                        )
                        await qr_img_locator.wait_for(state="visible", timeout=5000)
                        qr_src = await qr_img_locator.first.get_attribute("src")
                        if qr_src and qr_src.startswith("data:image/"):
                            base64_data = qr_src.split(",")[1]
                            return {
                                "status": "UPI QR Code generated successfully. Show it to the customer.",
                                "qr_base64": base64_data,
                                "format": qr_src.split(";")[0].split("/")[1],
                            }
                    except Exception as qr_e:
                        print(f"Failed to extract QR Code image: {qr_e}")

                    return (
                        "UPI QR Code generated successfully. Show it to the customer."
                    )
                else:
                    print("Generate QR button not found within UPI.")
                    return "ERROR: UPI section opened but 'Generate QR' button not found."
            else:
                print("UPI option not found.")
                return "ERROR: UPI option not found in payment widget."

        except Exception as e:
            print(f"Error selecting payment method: {e}")
            return f"ERROR: {str(e)}"

    async def click_pay_now(self):
        """Clicks the final Pay Now button."""
        try:
            # Strategy 1: Specific class partial match
            pay_btn_specific = self.page.locator(
                "div[class*='Zpayments__Button']:has-text('Pay Now')"
            )
            if (
                await pay_btn_specific.count() > 0
                and await pay_btn_specific.first.is_visible()
            ):
                await pay_btn_specific.first.click()
                print("Clicked 'Pay Now'. Please approve the payment on your UPI app.")
                return "Clicked Pay Now."

            # Strategy 2: the Pay Now container (confirmed class on the live
            # checkout page). Replaces a previous broad `div, button` text match
            # with `.last`, which could land on the wrong element on a money
            # path. We prefer to fail (returning an error) over mis-clicking.
            pay_btn_container = self.page.locator(
                "div[class*='Zpayments__PayNowButtonContainer']"
            )
            if (
                await pay_btn_container.count() > 0
                and await pay_btn_container.first.is_visible()
            ):
                await pay_btn_container.first.click()
                print("Clicked 'Pay Now'.")
                return "Clicked Pay Now."

            # Strategy 3: Check inside iframe
            iframe_element = await self.page.query_selector("#payment_widget")
            if iframe_element:
                frame = await iframe_element.content_frame()
                if frame:
                    # NOTE: "text='Pay Now', text='Place Order'" is NOT a valid
                    # Playwright union selector and never matched. Use two valid
                    # lookups instead (same intent: click whichever exists).
                    frame_pay_now = frame.locator("text='Pay Now'")
                    if await frame_pay_now.count() > 0:
                        await frame_pay_now.first.click()
                        print("Clicked payment button inside iframe.")
                        return "Clicked payment button inside iframe."

                    frame_place_order = frame.locator("text='Place Order'")
                    if await frame_place_order.count() > 0:
                        await frame_place_order.first.click()
                        print("Clicked payment button inside iframe.")
                        return "Clicked payment button inside iframe."

            print("Could not find 'Pay Now' button (timeout or not in DOM).")
            return "ERROR: Could not find Pay Now button."

        except Exception as e:
            print(f"Error clicking Pay Now: {e}")
            return f"ERROR: {str(e)}"
