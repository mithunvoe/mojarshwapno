"""Scrape the Shwapno databreach checker for a single phone number."""

import re
import time
import requests
from dataclasses import dataclass, field
from bs4 import BeautifulSoup

BASE_URL = "https://shwapnocheck.2bd.net/"


@dataclass(frozen=True)
class PurchaseItem:
    product: str
    date: str
    quantity: str
    price: str
    category: str


@dataclass(frozen=True)
class CheckResult:
    phone: str
    found: bool
    name: str = ""
    code: str = ""
    mobile: str = ""
    item_count: int = 0
    purchases: tuple[PurchaseItem, ...] = ()
    error: str = ""


def _get_csrf_and_session() -> tuple[requests.Session, str]:
    """Create a new session and fetch a fresh CSRF token."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Referer": BASE_URL,
        "Origin": "https://shwapnocheck.2bd.net",
    })
    resp = session.get(BASE_URL, timeout=15)
    resp.raise_for_status()
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not find CSRF token on page")
    return session, match.group(1)


def _parse_response(html: str, phone: str) -> CheckResult:
    """Parse the HTML response into a CheckResult."""
    soup = BeautifulSoup(html, "html.parser")

    # Check if customer info section exists
    info_heading = soup.find("h2", string=re.compile(r"Customer Info"))
    if not info_heading:
        return CheckResult(phone=phone, found=False)

    # Extract customer info
    info_rows = soup.select(".info-row")
    name = code = mobile = ""
    for row in info_rows:
        label_el = row.select_one(".label")
        value_el = row.select_one(".value")
        if not label_el or not value_el:
            continue
        label = label_el.get_text(strip=True)
        value = value_el.get_text(strip=True)
        if label == "Name":
            name = value
        elif label == "Code":
            code = value
        elif label == "Mobile":
            mobile = value

    # Extract purchase items
    purchases = []
    for item_div in soup.select(".purchase-item"):
        product_el = item_div.select_one(".product-name")
        product = product_el.get_text(strip=True) if product_el else ""

        meta_spans = item_div.select(".purchase-meta span")
        date = qty = price = category = ""
        for span in meta_spans:
            text = span.get_text(strip=True)
            if text.startswith("\U0001f4c5"):  # calendar emoji
                date = text.replace("\U0001f4c5", "").strip()
            elif text.startswith("\U0001f4e6"):  # package emoji
                qty = text.replace("\U0001f4e6", "").replace("Qty:", "").strip()
            elif text.startswith("\U0001f4b0"):  # money bag emoji
                price = text.replace("\U0001f4b0", "").strip()
            elif span.get("class") and "badge" in span.get("class", []):
                category = text

        purchases.append(PurchaseItem(
            product=product, date=date, quantity=qty, price=price, category=category,
        ))

    # Extract item count from summary
    summary_el = soup.select_one(".summary")
    item_count = 0
    if summary_el:
        m = re.search(r"(\d+)\s*item", summary_el.get_text())
        if m:
            item_count = int(m.group(1))

    return CheckResult(
        phone=phone,
        found=True,
        name=name,
        code=code,
        mobile=mobile,
        item_count=item_count,
        purchases=tuple(purchases),
    )


def check_phone(phone: str, max_retries: int = 5, retry_delay: float = 2.0) -> CheckResult:
    """Check a phone number against the Shwapno databreach checker.

    Retries on failure (403, network errors) up to max_retries times.
    Each attempt uses a fresh session + CSRF token.
    """
    last_error = ""
    best_result: CheckResult | None = None

    for attempt in range(max_retries):
        try:
            session, csrf = _get_csrf_and_session()
            resp = session.post(
                BASE_URL,
                data={"csrf_token": csrf, "q": phone},
                timeout=30,
            )

            if resp.status_code == 403:
                last_error = f"403 Forbidden (attempt {attempt + 1})"
                time.sleep(retry_delay)
                continue

            resp.raise_for_status()

            if "Customer Info" in resp.text:
                result = _parse_response(resp.text, phone)
                # If we got items, this is a complete response - return immediately
                if result.item_count > 0:
                    return result
                # Got customer info but no items - partial response, keep as best so far and retry
                if best_result is None or result.item_count > best_result.item_count:
                    best_result = result
                last_error = f"Partial response, 0 items (attempt {attempt + 1})"
                time.sleep(retry_delay)
                continue

            # 200 but no "Customer Info" at all - could be a flaky empty page or genuinely not found
            # Check if the search form has our number echoed back (confirms server processed it)
            if f'value="{phone}"' in resp.text:
                # Server processed the request and returned no data - number is safe
                return CheckResult(phone=phone, found=False)

            # Server returned 200 but didn't seem to process our request - retry
            last_error = f"Empty/unexpected 200 response (attempt {attempt + 1})"
            time.sleep(retry_delay)
            continue

        except requests.RequestException as e:
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(retry_delay)
            continue

    # If we got a partial result (customer info but no items), return it rather than nothing
    if best_result is not None:
        return best_result

    return CheckResult(phone=phone, found=False, error=f"Failed after {max_retries} retries: {last_error}")
