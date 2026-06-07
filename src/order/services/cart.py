from .base import BaseService


class CartService(BaseService):
    async def _dismiss_overlays(self):
        """Dismiss any popups, modals, or overlays that may block interaction."""
        try:
            for selector in [
                "button[aria-label='close']",
                "div[class*='Modal'] button",
                "div[class*='Overlay'] button",
                "button:has-text('✕')",
                "button:has-text('×')",
            ]:
                if await self.page.is_visible(selector):
                    await self.page.click(selector, timeout=2000)
                    await self.page.wait_for_timeout(300)
        except Exception:
            pass

    async def add_to_cart(self, product_id: str, quantity: int = 1):
        """Adds a product to the cart by its unique ID. Supports multiple quantities."""
        print(f"Adding product with ID {product_id} to cart (Quantity: {quantity})...")
        try:
            # Dismiss any overlays that might block buttons
            await self._dismiss_overlays()

            # Target the specific card by ID
            card = self.page.locator(f"div[id='{product_id}']")

            if await card.count() == 0:
                print(f"Product ID {product_id} not found on current page.")

                # Check if we know this product from a previous search
                if self.manager and product_id in self.manager.known_products:
                    print("Product found in history.")
                    product_info = self.manager.known_products[product_id]
                    source_query = product_info.get("source_query")

                    if source_query:
                        print(
                            f"Navigating back to search results for '{source_query}'..."
                        )
                        # Delegate search back to manager/search service
                        if hasattr(self.manager, "search_product"):
                            await self.manager.search_product(source_query)

                        # Re-locate the card after search
                        card = self.page.locator(f"div[id='{product_id}']")
                        if await card.count() == 0:
                            print(
                                f"CRITICAL: Product {product_id} still not found after re-search."
                            )
                            return
                    else:
                        print("No source query found for this product.")
                        return
                else:
                    print("Product ID unknown and not on current page.")
                    return

            # Dismiss overlays again after potential re-search
            await self._dismiss_overlays()

            # Find the ADD button specifically inside the card
            add_btn = card.locator("div").filter(has_text="ADD").last

            items_to_add = quantity

            # If ADD button is visible, click it once to start
            if await add_btn.is_visible():
                clicked = await self._safe_click(
                    add_btn, f"ADD button for {product_id}"
                )
                if clicked:
                    print(f"Clicked ADD button for {product_id} (1/{quantity}).")
                    items_to_add -= 1
                    # Wait for the counter to appear
                    await self.page.wait_for_timeout(500)
                else:
                    print(f"Failed to click ADD button for {product_id}.")
                    return

            # Use increment button for remaining quantity
            if items_to_add > 0:
                # Wait for the counter to initialize
                await self.page.wait_for_timeout(1000)

                # Robust strategy to find the + button
                plus_btn = card.locator(".icon-plus").first
                if await plus_btn.count() > 0:
                    plus_btn = plus_btn.locator("..")
                else:
                    plus_btn = card.locator("text='+'").first

                if await plus_btn.is_visible():
                    for i in range(items_to_add):
                        await self._safe_click(plus_btn, f"+ button for {product_id}")
                        print(
                            f"Incrementing quantity for {product_id} ({quantity - items_to_add + i + 1}/{quantity})."
                        )
                        # Check for limit reached
                        try:
                            limit_msg = self.page.get_by_text(
                                "Sorry, you can't add more of this item"
                            )
                            if await limit_msg.is_visible(timeout=1000):
                                print(f"Quantity limit reached for {product_id}.")
                                break
                        except Exception:
                            pass

                        await self.page.wait_for_timeout(500)
                else:
                    print(
                        f"Could not find '+' button to add remaining quantity for {product_id}."
                    )

            await self.page.wait_for_timeout(1000)

            # Check for "Store Unavailable" modal
            if await self.page.is_visible(
                "div:has-text('Sorry, can\\'t take your order')"
            ):
                print("WARNING: Store is unavailable (Modal detected).")
                return

        except Exception as e:
            print(f"ERROR: Failed to add to cart: {e}")

    async def remove_from_cart(self, product_id: str, quantity: int = 1):
        """Removes a specific quantity of a product from the cart."""
        print(f"Removing {quantity} of product ID {product_id} from cart...")
        try:
            # Dismiss any overlays
            await self._dismiss_overlays()

            # Target the specific card by ID
            card = self.page.locator(f"div[id='{product_id}']")

            if await card.count() == 0:
                # Attempt recovery via search if known
                if self.manager and product_id in self.manager.known_products:
                    product_info = self.manager.known_products[product_id]
                    source_query = product_info.get("source_query")
                    if source_query:
                        if hasattr(self.manager, "search_product"):
                            await self.manager.search_product(source_query)
                        card = self.page.locator(f"div[id='{product_id}']")
                        if await card.count() == 0:
                            print(
                                f"Product {product_id} not found after recovery search."
                            )
                            return
                else:
                    print(f"Product ID {product_id} not found and unknown.")
                    return

            # Check for decrement button
            minus_btn = card.locator(".icon-minus").first
            if await minus_btn.count() > 0:
                minus_btn = minus_btn.locator("..")
            else:
                minus_btn = card.locator("text='-'").first

            if await minus_btn.is_visible():
                for i in range(quantity):
                    await self._safe_click(minus_btn, f"- button for {product_id}")
                    print(
                        f"Decrementing quantity for {product_id} ({i + 1}/{quantity})."
                    )
                    await self.page.wait_for_timeout(500)

                    # If ADD button reappears, item is fully removed
                    if (
                        await card.locator("div")
                        .filter(has_text="ADD")
                        .last.is_visible()
                    ):
                        print(f"Item {product_id} completely removed from cart.")
                        break
            else:
                print(f"Item {product_id} is not in cart (no '-' button found).")

        except Exception as e:
            print(f"ERROR: Failed to remove from cart: {e}")

    async def _cart_is_empty(self):
        """True if the header cart button shows an empty cart.

        With items the button reads "N item(s) / price"; empty it reads
        "My Cart". The drawer refuses to open at all on an empty cart, so
        this is how callers distinguish "empty" from "drawer failed to open".
        """
        try:
            btn = self.page.locator("div[class*='CartButton__Container']").first
            if await btn.count() == 0:
                return False
            text = (await btn.inner_text()).lower()
            return "my cart" in text and "item" not in text
        except Exception:
            return False

    async def _open_cart(self):
        """Make the cart visible and return its root locator.

        Tries the open drawer, then clicks the cart button (retrying once).
        Returns None if the drawer never appears. Navigating to /cart is NOT a
        fallback: that route does not exist on desktop web and redirects back
        to the homepage, which previously made callers parse homepage text as
        if it were the cart.
        """
        await self._dismiss_overlays()
        drawer_sel = (
            "div[class*='CartDrawer'], div[class*='CartSidebar'], "
            "div.cart-modal-rn, div[class*='CartWrapper__CartContainer']"
        )
        drawer = self.page.locator(drawer_sel).first
        if await drawer.is_visible():
            return drawer

        # The drawer refuses to open on an empty cart, so don't burn two click
        # attempts to learn what the header button already says.
        if await self._cart_is_empty():
            return None

        # Click the cart button (robust click; plain clicks get eaten on some
        # pages). Retry once: the header re-renders with the delivery ETA and
        # can swallow the first click.
        cart_btn = self.page.locator(
            "div[class*='CartButton__Button'], div[class*='CartButton__Container'], a[href='/cart']"
        ).first
        for attempt in ("cart button", "cart button (retry)"):
            if await cart_btn.count() == 0:
                break
            await self._safe_click(cart_btn, attempt)
            await self.page.wait_for_timeout(2000)
            if await drawer.is_visible():
                return drawer
        return None

    async def _find_cart_rows(self, root, needle_tokens, needle_str):
        """Return a list of (row_locator, label) for every cart line whose
        combined title + variant text matches the query.

        Matches on title AND variant so a pack size (e.g. "500 ml") both matches
        and distinguishes variants of the same product. Re-resolved fresh on
        every call: cart rows are live locators whose index shifts as items are
        removed, so a cached positional row must never be reused across a click.
        """
        items = root.locator("div[class*='CartProduct__Container']")
        if await items.count() == 0:
            items = root.locator("div[class*='DefaultProductCard__Container']")
        count = await items.count()
        matches = []
        for i in range(count):
            item = items.nth(i)
            title_el = item.locator("div[class*='ProductTitle']")
            if await title_el.count() > 0:
                title = await title_el.first.inner_text()
            else:
                title = await item.inner_text()
            variant_el = item.locator("div[class*='ProductVariant']")
            variant = (
                await variant_el.first.inner_text()
                if await variant_el.count() > 0
                else ""
            )
            row_text = " ".join(f"{title} {variant}".lower().split())
            if (needle_str and needle_str in row_text) or (
                needle_tokens and all(t in row_text for t in needle_tokens)
            ):
                label = title.strip().split("\n")[0]
                v = variant.strip().split("\n")[0]
                if v:
                    label = f"{label} | {v}"
                matches.append((item, label))
        return matches

    async def _find_minus_btn(self, root):
        """Resolve the decrement (-) control under `root`.

        Search-page product cards render it as an .icon-minus glyph; cart
        drawer line items render the -/+ pair as AddToCart__AddMinusIcon divs
        laid out as [- qty +]. Don't trust DOM order for which icon is the
        minus: validate by position and take the LEFTMOST of the pair. A lone
        AddMinusIcon is ambiguous (could be the plus), so refuse it rather
        than risk incrementing on a removal path. Returns a clickable locator,
        or None.
        """
        minus = root.locator(".icon-minus").first
        if await minus.count() > 0:
            return minus.locator("..")
        icons = root.locator("div[class*='AddMinusIcon']")
        n = await icons.count()
        if n >= 2:
            # Pick the leftmost icon by geometry, considering only visible
            # icons with a real bounding box. Refuse to click if fewer than
            # two have usable geometry: a guess on a removal path could hit
            # the plus and increment instead.
            best = None
            usable = 0
            for i in range(n):
                icon = icons.nth(i)
                if not await icon.is_visible():
                    continue
                box = await icon.bounding_box()
                if not box:
                    continue
                usable += 1
                if best is None or box["x"] < best[0]:
                    best = (box["x"], icon)
            if best is not None and usable >= 2:
                return best[1].locator("..")
            print("AddMinusIcon geometry ambiguous; refusing to click.")
        elif n == 1:
            print("Single AddMinusIcon found; ambiguous (- or +), refusing to click.")
        minus = root.locator("text='-'").first
        if await minus.count() > 0:
            return minus
        return None

    async def remove_cart_item_by_name(self, name: str, quantity=None):
        """Remove a cart line item by matching its title + variant text.

        Works for any pack size / variant because it clicks the minus button
        inside the matched cart line item itself, instead of locating a product
        card by ID (which fails when the in-cart pack differs from the product
        card's default variant). `name` is matched case-insensitively against
        title + variant; include the pack size (e.g. "Amul Gold 500 ml") to pick
        a specific variant. If the query matches more than one cart line, it
        refuses and asks for a more specific name rather than guessing.
        quantity=None removes the item entirely.
        """
        print(f"Removing cart item matching '{name}'...")
        try:
            root = await self._open_cart()
            if root is None:
                if await self._cart_is_empty():
                    return f"ERROR: Cart is empty; nothing matches '{name}'."
                return "ERROR: Could not open the cart."

            # Normalize the query: drop a pasted price/qty tail from check_cart's
            # "Title | Variant | Rs.. | Qty: .." format, strip the "|" separators,
            # then match on the remaining title+variant tokens.
            raw = name.strip().lower()
            # Strip a leading list marker so a pasted check_cart bullet
            # ("• Amul Gold | 500 ml | ...") still matches.
            raw = raw.lstrip("•*-·∙ \t")
            for cut in ("| ₹", "|₹", " ₹", "| qty", "|qty", " qty"):
                idx = raw.find(cut)
                if idx != -1:
                    raw = raw[:idx]
            needle_str = " ".join(raw.replace("|", " ").split())
            needle_tokens = needle_str.split()
            if not needle_tokens:
                return "ERROR: Empty item name."

            matches = await self._find_cart_rows(root, needle_tokens, needle_str)
            if not matches:
                return (
                    f"ERROR: No cart item matching '{name}' found. "
                    "Call check_cart to see exact item names."
                )
            if len(matches) > 1:
                labels = "; ".join(lbl for _, lbl in matches)
                return (
                    f"ERROR: '{name}' matches {len(matches)} cart items ({labels}). "
                    "Pass a more specific name including the pack size to pick one."
                )

            target_title = matches[0][1]

            # Click minus until the matched item is gone, or `quantity` units
            # removed. CRITICAL: re-find the row by title+variant every pass.
            # Rows are live locators that shift index when one is removed, so
            # reusing a positional locator could drift onto and delete a
            # DIFFERENT item (it would empty the whole cart). Re-matching each
            # pass only ever clicks the intended item's minus; stop when it is
            # gone (0 matches) or shows ADD with no minus. A >1 match mid-loop
            # (should not happen after the up-front check) also stops safely.
            max_clicks = quantity if quantity else 30
            clicks = 0
            for _ in range(max_clicks):
                rows = await self._find_cart_rows(root, needle_tokens, needle_str)
                if len(rows) != 1:
                    break
                row = rows[0][0]

                qty_container = row.locator(
                    "div[class*='AddToCart__UpdatedButtonContainer']"
                ).first
                btn_root = qty_container if await qty_container.count() > 0 else row
                minus_btn = await self._find_minus_btn(btn_root)

                # No decrement control (e.g. the row now shows ADD) => done.
                if minus_btn is None or not await minus_btn.is_visible():
                    break

                await self._safe_click(minus_btn, f"- button for {target_title}")
                clicks += 1
                await self.page.wait_for_timeout(600)

            if clicks == 0:
                return f"ERROR: Found '{target_title}' but no decrement (-) button on it."

            # Removing entirely (quantity=None): confirm the row is actually gone
            # before claiming success. A line whose qty exceeded the click cap
            # would otherwise be reported as removed while still in the cart.
            if quantity is None:
                if await self._find_cart_rows(root, needle_tokens, needle_str):
                    return (
                        f"WARNING: clicked minus {clicks}x on '{target_title}' but it is still "
                        "in the cart. Call remove_cart_item again to finish removing it."
                    )
                print(f"Removed '{target_title}' from cart.")
                return f"Removed '{target_title}' from cart."

            print(f"Removed {clicks} unit(s) of '{target_title}' from cart.")
            return f"Removed {clicks} unit(s) of '{target_title}' from cart."
        except Exception as e:
            return f"ERROR: Failed to remove cart item: {e}"

    async def get_cart_items(self):
        """Checks items in the cart and returns the text content."""
        try:
            # Open the cart via the shared robust path (drawer -> cart button
            # -> full /cart page). check_cart used to do a single fragile click
            # that timed out intermittently; reuse the same opener as removal.
            drawer = await self._open_cart()
            if drawer is None:
                if await self._cart_is_empty():
                    return "Cart is empty."
                return "ERROR: Cart drawer did not open."

            # Verify availability
            if (
                await self.page.is_visible("text=Sorry, can't take your order")
                or await self.page.is_visible("text=Currently unavailable")
                or await self.page.is_visible("text=High Demand")
            ):
                return "CRITICAL: Store is unavailable. 'Sorry, can't take your order'. Please try again later."

            if await self._is_store_closed():
                return "CRITICAL: Store is closed."

            # Scrape content more cleanly using evaluate to extract meaningful parts
            content = await drawer.evaluate("""(drawer) => {
                let text = drawer.innerText;
                let results = ["--- CART DETAILS ---"];
                
                // Try to extract items. One cart item renders as a
                // CartProduct__Container wrapping a DefaultProductCard__Container,
                // so the old union selector matched both and listed every item
                // twice. Prefer the outer wrapper (one per item) and fall back to
                // the inner card for layouts without the wrapper.
                let items = drawer.querySelectorAll("div[class*='CartProduct__Container']");
                if (items.length === 0) {
                    items = drawer.querySelectorAll("div[class*='DefaultProductCard__Container']");
                }
                items.forEach(item => {
                    let title = item.querySelector("div[class*='ProductTitle']")?.innerText || "";
                    let variant = item.querySelector("div[class*='ProductVariant']")?.innerText || "";
                    let price = item.querySelector("div[class*='Price-']")?.innerText || "";
                    // Quantity is a bare text node inside the qty container,
                    // sandwiched between the - and + buttons. Those buttons
                    // render as icon-font glyphs (not literal +/-), so read only
                    // the container's direct text nodes and keep the digits.
                    let qtyContainer = item.querySelector("div[class*='AddToCart__UpdatedButtonContainer']");
                    let qty = "1";
                    if (qtyContainer) {
                        let direct = Array.from(qtyContainer.childNodes)
                            .filter(n => n.nodeType === 3)
                            .map(n => n.textContent.trim())
                            .join("");
                        let digits = direct.replace(/[^0-9]/g, '');
                        if (digits) qty = digits;
                    }
                    if (title) {
                        results.push(`• ${title} | ${variant} | ${price} | Qty: ${qty}`);
                    }
                });
                
                if (items.length === 0) {
                    results.push("Raw text: " + text.substring(0, 300) + "...");
                }
                
                // Try to extract Bill Details
                let billItems = drawer.querySelectorAll("div[class*='BillCard__BillItemContainer']");
                if (billItems.length > 0) results.push("\\n--- BILL DETAILS ---");
                billItems.forEach(item => {
                    let textParts = item.innerText.split('\\n').map(t => t.trim()).filter(t => t);
                    if (textParts.length >= 2) {
                        results.push(`${textParts[0]}: ${textParts[textParts.length-1]}`);
                    }
                });
                
                // Get Delivery Address
                let addressHeading = drawer.querySelector("div[class*='ListStrip__Heading']")?.innerText || "";
                let addressSub = drawer.querySelector("div[class*='ListStrip__SubHeading']")?.innerText || "";
                if (addressHeading) {
                    results.push("\\n--- DELIVERY TO ---");
                    results.push(`${addressHeading} - ${addressSub}`);
                }
                
                // Get Total
                let totalText = drawer.querySelector("div[class*='CheckoutStrip__TotalText']")?.innerText || "";
                let finalPrice = drawer.querySelector("div[class*='CheckoutStrip__NetPriceText']")?.innerText || "";
                if (finalPrice) {
                    results.push(`\\n--- TOTAL TO PAY: ${finalPrice} ---`);
                }
                
                return results.join('\\n');
            }""")

            if "Currently unavailable" in content or "can't take your order" in content:
                return (
                    "CRITICAL: Store is unavailable. Please try again later.\\n"
                    + content
                )

            return content

        except Exception as e:
            return f"ERROR: Failed to get cart items: {e}"
