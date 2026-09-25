import os
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
CATEGORY_URL = f"{BASE_URL}/thuc-pham-chuc-nang/vitamin-khoang-chat"
# https://nhathuoclongchau.com.vn/thuc-pham-chuc-nang/vitamin-khoang-chat
MAX_PRODUCTS = 30          # Đặt None để cào hết
MAX_LOAD_MORE = 20
OUTPUT_FILE = "products.xlsx"
DEBUG_DIR = "debug"
HEADLESS = False           # Đổi thành True khi chạy ổn định
PAGE_LOAD_TIMEOUT = 60000
ELEMENT_TIMEOUT = 30000
LOAD_MORE_TIMEOUT = 20000
NETWORK_IDLE_TIMEOUT = 10000
DELAY_MIN, DELAY_MAX = 3.0, 6.0
LOAD_MORE_DELAY_MIN, LOAD_MORE_DELAY_MAX = 2.0, 4.0

SECTION = "#category-page__products-section"
CARD_LINK = f'{SECTION} a[href$=".html"]'
API_HINT = "search-product-service"   # API danh sách sản phẩm (thấy trong runtimeConfig)

COLUMNS = ["url", "name", "sku", "price_text", "price",
           "original_price", "image", "error"]

# JS đếm số href KHÁC NHAU (mỗi card có 2 thẻ <a> trỏ cùng 1 link)
JS_DISTINCT = """([sel, n]) =>
    new Set([...document.querySelectorAll(sel)].map(a => a.getAttribute('href'))).size > n"""

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

def save_debug(page, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}_{int(time.time())}.png")
    try:
        page.screenshot(path=path, full_page=True)
        print(f"  [debug] Đã chụp màn hình: {path}")
    except Exception:
        pass

def extract_slugs(data, out):
    """Duyệt đệ quy JSON, lấy mọi giá trị 'slug' kết thúc bằng .html"""
    if isinstance(data, dict):
        slug = data.get("slug")
        if isinstance(slug, str) and slug.endswith(".html"):
            out.append(slug)
        for v in data.values():
            extract_slugs(v, out)
    elif isinstance(data, list):
        for v in data:
            extract_slugs(v, out)

def launch_browser(playwright):
    """Tạo trình duyệt + context + trang mới"""
    browser = playwright.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
    )
    page = context.new_page()
    apply_stealth(page)
    return browser, context, page

# ======================================================================
# THU THẬP LINK SẢN PHẨM
# ======================================================================
def collect_product_links(page, max_products=None):
    links = {}        # dict giữ thứ tự, dùng như ordered set
    api_slugs = []

    def on_response(resp):
        if API_HINT not in resp.url:
            return
        try:
            extract_slugs(resp.json(), api_slugs)
        except Exception:
            pass  # response không phải JSON

    page.on("response", on_response)

    def harvest():
        """Gom link từ DOM + từ API vào `links`, trả về tổng số link"""
        try:
            hrefs = page.locator(CARD_LINK).evaluate_all(
                "els => els.map(e => e.getAttribute('href'))"
            )
        except Exception:
            hrefs = []
        for h in hrefs:
            if h:
                links.setdefault(urljoin(BASE_URL, h.strip()), None)
        for s in api_slugs:
            links.setdefault(urljoin(BASE_URL + "/", s.lstrip("/")), None)
        return len(links)

    def dom_distinct():
        return page.evaluate(
            "sel => new Set([...document.querySelectorAll(sel)].map(a => a.getAttribute('href'))).size",
            CARD_LINK,
        )

    try:
        page.goto(CATEGORY_URL, timeout=PAGE_LOAD_TIMEOUT)
        wait_page_ready(page)
        page.locator(CARD_LINK).first.wait_for(timeout=ELEMENT_TIMEOUT)

        for round_no in range(1, MAX_LOAD_MORE + 1):
            total = harvest()
            print(f"  Vòng {round_no}: đã gom {total} link")
            if max_products and total >= max_products:
                break

            human_scroll(page)
            load_more = page.locator(
                f"{SECTION} button",
                has_text=re.compile(r"Xem thêm\s*\d+\s*sản phẩm"),
            )
            if load_more.count() == 0:
                print("  Hết nút 'Xem thêm' -> đã tải toàn bộ danh mục")
                break

            before_dom = dom_distinct()
            btn = load_more.first
            btn.scroll_into_view_if_needed()
            random_sleep(0.5, 1.0)
            btn.click()

            try:
                page.wait_for_function(JS_DISTINCT, arg=[CARD_LINK, before_dom],
                                       timeout=LOAD_MORE_TIMEOUT)
            except PWTimeout:
                # DOM không tăng — kiểm tra xem API có trả thêm dữ liệu không
                if harvest() <= total:
                    print("  Không tải thêm được sản phẩm, dừng lại")
                    save_debug(page, "load_more_fail")
                    break

            random_sleep(LOAD_MORE_DELAY_MIN, LOAD_MORE_DELAY_MAX)

        harvest()  # gom lần cuối
    finally:
        page.remove_listener("response", on_response)

    result = list(links)
    return result[:max_products] if max_products else result

# ======================================================================
# CÀO CHI TIẾT SẢN PHẨM
# ======================================================================
def scrape_product(page, url):
    page.goto(url, timeout=PAGE_LOAD_TIMEOUT)
    wait_page_ready(page)
    try:
        page.locator('[data-test="product_name"]').first.wait_for(timeout=ELEMENT_TIMEOUT)
    except PWTimeout:
        save_debug(page, "product_fail")
        raise
    human_scroll(page)

    price_text = get_text(page, '[data-test="price"]')
    original_text = get_text(page, '[data-test="strike_price"]')

    return {
        "url": page.url,
        "name": get_text(page, '[data-test="product_name"]') or get_text(page, "h1"),
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
        # === Bước 1: Lấy danh sách link ===
        print("Bước 1: Thu thập link sản phẩm...")
        browser, context, page = launch_browser(p)
        try:
            links = collect_product_links(page, MAX_PRODUCTS)
            print(f"-> Thu được {len(links)} link\n")
        finally:
            browser.close()

        if not links:
            print(f"Không thu được link nào. Xem ảnh trong thư mục '{DEBUG_DIR}/' để kiểm tra.")
            return

        # === Bước 2: Cào chi tiết — mỗi sản phẩm = 1 trình duyệt mới ===
        print("Bước 2: Cào chi tiết từng sản phẩm (mỗi link = trình duyệt mới)...")
        for i, url in enumerate(links, start=1):
            brw = None
            try:
                brw, ctx, pg = launch_browser(p)
                product = scrape_product(pg, url)
                name = product["name"] or ""
                print(f"[{i}/{len(links)}] OK  - {name[:50] + ('...' if len(name) > 50 else '')}")
            except Exception as e:
                product = {"url": url, "error": str(e)[:200]}
                print(f"[{i}/{len(links)}] LỖI - {url} — {str(e)[:100]}")
            finally:
                if brw:
                    brw.close()

            results.append(product)
            random_sleep(DELAY_MIN, DELAY_MAX)

    # === Lưu kết quả (cột cố định -> không còn KeyError) ===
    df = pd.DataFrame(results, columns=COLUMNS)
    df.to_excel(OUTPUT_FILE, index=False)
    ok = df["error"].isna().sum()
    print(f"\n✅ Xuất {len(df)} dòng ({ok} thành công) ra {OUTPUT_FILE}")

if __name__ == "__main__":
    main()