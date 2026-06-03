# Blinkit MCP — Agent Operating Guide

You have access to an unofficial Blinkit MCP server. It controls a real **Firefox
browser** (via Playwright) on the user's machine and shops on **blinkit.com** as
the logged-in user. Actions are real: adding to cart, and especially paying,
affect a real account and place real orders. Treat it as a money-capable tool.

## Core facts

- It drives an actual browser session, not an API. One logged-in Blinkit account.
  Login persists between runs (saved session), so you usually won't need to log in.
- Calls run **one at a time** (serialized) on a shared browser. Don't fire tools in
  parallel. The browser launches on the first call, so the first call can be slow.
- Failures come back prefixed with `ERROR:` or `CRITICAL:` (e.g.
  `CRITICAL: Store is closed.`). Don't treat those as success.
- Tools may appear name-prefixed in your client (e.g. `mcp__blinkit-mcp__search`);
  base names are listed below.

## The 14 tools

- `check_login` → "Logged In" / "Not Logged In".
- `login(phone_number)` → starts login; the OTP is sent to the user's phone.
- `enter_otp(otp)` → completes login, saves the session.
- `set_location(location_name)` → set delivery location by search; pass `"detect"`
  to use "Detect my location".
- `search(query)` → returns a list of items, each with an **id**, name, price.
- `add_to_cart(item_id, quantity=1)` → add by the **item id from search**
  (NOT the list index/position).
- `remove_from_cart(item_id, quantity=1)`.
- `check_cart` → items, total, and the current delivery address.
- `get_addresses` → saved addresses, each with an index.
- `select_address(index)` → pick a delivery address. Use this **before** checkout.
- `checkout` → advances the cart to the payment screen ("Proceed To Pay").
  Does **not** pay.
- `proceed_to_pay` → advances again (use after changing address). Does **not** pay.
- `select_payment_method` → auto-selects Cash on Delivery if available; otherwise
  opens UPI and generates a **QR code** (saved and opened as an image for the user
  to scan). Does **not** pay.
- `pay_now` → clicks the final "Pay Now". **This is the only tool that commits a
  real payment.**

## Normal order sequence

1. `check_login` → if not logged in: `login(phone)` then `enter_otp(otp)`.
2. `set_location("detect")` (or a specific area) if the location is wrong.
3. `search("milk")` → take the **id** of the item you want.
4. `add_to_cart(id, quantity)`.
5. `check_cart` → confirm items, total, and delivery address.
6. If the address is wrong: `get_addresses` → `select_address(index)` — do this
   **before** `checkout`, never after.
7. `checkout` → reaches the payment screen.
8. `select_payment_method` → Cash on Delivery, or a UPI QR for the user to scan.
9. `pay_now` → **only after the user explicitly confirms they want to pay.**

## Hard rules

- Never call `pay_now` without explicit user confirmation — it spends real money.
- Set/fix the delivery address **before** `checkout`, not after.
- Use the item **id** from `search` for `add_to_cart`, not the position number.
- Cash on Delivery is unavailable on orders under ₹50; it falls back to UPI QR.
- If a tool returns `ERROR:` / `CRITICAL:`, stop and report it rather than continuing.
