import re
import time
import random
from urllib.parse import urljoin
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ======================================================================
# CẤU HÌNH
# ======================================================================
BASE_URL = "https://nhathuoclongchau.com.vn"
CATEGORY_URL = f"{BASE_URL}/thuc-pham-chuc-nang"
MAX_PRODUCTS = 30          # Đặt None để cào hết
MAX_LOAD_MORE = 20
OUTPUT_FILE = "products.xlsx"
HEADLESS = False           # Đổi thành True khi chạy ổn định

PAGE_LOAD_TIMEOUT = 60000
ELEMENT_TIMEOUT = 30000
LOAD_MORE_TIMEOUT = 20000
NETWORK_IDLE_TIMEOUT = 10000

DELAY_MIN, DELAY_MAX = 3.0, 6.0
LOAD_MORE_DELAY_MIN, LOAD_MORE_DELAY_MAX = 2.0, 4.0

CARD_LINK = '#category-page__products-section a[href*=".html"]'

# ======================================================================
# HÀM TIỆN ÍCH & CHE GIẤU BOT
# ======================================================================
def apply_stealth(page):
    """Che giấu dấu hiệu bot — không cần thư viện ngoài"""
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'en-US', 'en'] });
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
    """)

def get_text(page, selector):
    element = page.locator(selector)
    if element.count() == 0:
        return None
    return element.first.inner_text().strip()

def get_attribute(page, selector, attribute):
    element = page.locator(selector)
    if element.count() == 0:
        return None
    return element.first.get_attribute(attribute)

def parse_price(text):
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text.split("/")[0])
    return int(digits) if digits else None

def wait_page_ready(page):
    page.wait_for_load_state("load", timeout=PAGE_LOAD_TIMEOUT)
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
    except PWTimeout:
        pass

def random_sleep(low, high):
    time.sleep(random.uniform(low, high))

def human_scroll(page):
    """Cuộn trang tự nhiên như người dùng"""
    page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
    random_sleep(0.3, 0.8)
    page.evaluate("window.scrollBy(0, -window.innerHeight / 4)")

# ======================================================================
# THU THẬP LINK SẢN PHẨM
# ======================================================================
def collect_product_links(page, max_products=None):
    page.goto(CATEGORY_URL, timeout=PAGE_LOAD_TIMEOUT)
    wait_page_ready(page)
    page.locator(CARD_LINK).first.wait_for(timeout=ELEMENT_TIMEOUT)

    for _ in range(MAX_LOAD_MORE):
        current = page.locator(CARD_LINK).count() // 2
        print(f"  Đang có ~{current} sản phẩm trên trang")
        if max_products and current >= max_products:
            break

        human_scroll(page)

        load_more = page.locator(
            "#category-page__products-section button",
            has_text=re.compile(r"Xem thêm\s*\d+\s*sản phẩm"),
        )
        if load_more.count() == 0:
            print("  Hết nút 'Xem thêm' -> đã tải toàn bộ danh mục")
            break

        before = page.locator(CARD_LINK).count()
        load_more.first.scroll_into_view_if_needed()
        random_sleep(0.5, 1.0)
        load_more.first.click()

        try:
            page.wait_for_function(
                "([sel, n]) => document.querySelectorAll(sel).length > n",
                arg=[CARD_LINK, before],
                timeout=LOAD_MORE_TIMEOUT,
            )
        except PWTimeout:
            print("  Không tải thêm được sản phẩm, dừng lại")
            break
        random_sleep(LOAD_MORE_DELAY_MIN, LOAD_MORE_DELAY_MAX)

    hrefs = page.locator(CARD_LINK).evaluate_all(
        "els => els.map(e => e.getAttribute('href'))"
    )
    links = list(dict.fromkeys(urljoin(BASE_URL, h.strip()) for h in hrefs if h))
    return links[:max_products] if max_products else links

# ======================================================================
# CÀO CHI TIẾT SẢN PHẨM
# ======================================================================
def scrape_product(page, url):
    page.goto(url, timeout=PAGE_LOAD_TIMEOUT)
    wait_page_ready(page)
    page.locator('[data-test="product_name"]').first.wait_for(timeout=ELEMENT_TIMEOUT)

    human_scroll(page)

    price_text = get_text(page, '[data-test="price"]')
    original_text = get_text(page, '[data-test="strike_price"]')

    return {
        "url": page.url,
        "name": get_text(page, '[data-test="product_name"]'),
        "sku": get_text(page, '[data-test-id="sku"]'),
        "price_text": price_text,
        "price": parse_price(price_text),
        "original_price": parse_price(original_text),
        "image": get_attribute(page, 'meta[property="og:image"]', "content"),
        "error": None,
    }

# ======================================================================
# CHƯƠNG TRÌNH CHÍNH
# ======================================================================
def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )

        page = context.new_page()
        apply_stealth(page)  # Áp dụng che giấu bot

        try:
            print("Bước 1: Thu thập link sản phẩm...")
            links = collect_product_links(page, MAX_PRODUCTS)
            print(f"-> Thu được {len(links)} link\n")

            print("Bước 2: Cào chi tiết từng sản phẩm...")
            for i, url in enumerate(links, start=1):
                try:
                    product = scrape_product(page, url)
                    name_preview = (product['name'][:50] + "...") if product['name'] and len(product['name']) > 50 else product['name']
                    print(f"[{i}/{len(links)}] OK  - {name_preview}")
                except Exception as e:
                    product = {"url": url, "error": str(e)[:200]}
                    print(f"[{i}/{len(links)}] LỖI - {url}")
                results.append(product)
                random_sleep(DELAY_MIN, DELAY_MAX)

        except KeyboardInterrupt:
            print("\nNgười dùng dừng chương trình, đang lưu dữ liệu...")
        finally:
            browser.close()
            if results:
                df = pd.DataFrame(results)
                df.to_excel(OUTPUT_FILE, index=False)
                ok = df["error"].isna().sum()
                print(f"\n✅ Xuất {len(df)} dòng ({ok} thành công) ra {OUTPUT_FILE}")
            else:
                print("\nKhông có dữ liệu để xuất.")

if __name__ == "__main__":
    main()