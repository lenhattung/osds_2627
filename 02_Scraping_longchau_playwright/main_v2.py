"""
Cào nhiều sản phẩm từ trang danh mục Nhà thuốc Long Châu bằng Playwright.

Quy trình:
  1. Mở trang danh mục, bấm "Xem thêm" nhiều lần để lấy link sản phẩm.
  2. Truy cập từng link, trích xuất thông tin chi tiết.
  3. Xuất kết quả ra file Excel.

Cài đặt:
  pip install playwright pandas openpyxl
  playwright install chromium
"""

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

MAX_PRODUCTS = 30          # Số sản phẩm muốn cào; đặt None để cào hết
MAX_LOAD_MORE = 20         # Số lần tối đa bấm nút "Xem thêm"
OUTPUT_FILE = "products.xlsx"
HEADLESS = False           # True: chạy ẩn trình duyệt

# Thời gian chờ tối đa (mili-giây) – tăng lên nếu mạng chậm
PAGE_LOAD_TIMEOUT = 60000      # chờ tải trang: 60 giây
ELEMENT_TIMEOUT = 30000        # chờ phần tử xuất hiện: 30 giây
LOAD_MORE_TIMEOUT = 20000      # chờ sản phẩm mới sau khi bấm "Xem thêm": 20 giây
NETWORK_IDLE_TIMEOUT = 10000   # chờ mạng yên: 10 giây

# Thời gian nghỉ (giây)
DELAY_MIN, DELAY_MAX = 2.0, 4.0            # giữa các sản phẩm
LOAD_MORE_DELAY_MIN, LOAD_MORE_DELAY_MAX = 1.5, 3.0   # sau mỗi lần bấm "Xem thêm"

# Thẻ <a> dẫn tới trang chi tiết, nằm trong khu vực danh sách sản phẩm
CARD_LINK = '#category-page__products-section a[href*=".html"]'


# ======================================================================
# HÀM TIỆN ÍCH
# ======================================================================
def get_text(page, selector):
    """Lấy text của phần tử đầu tiên khớp selector, không có thì trả None."""
    element = page.locator(selector)
    if element.count() == 0:
        return None
    return element.first.inner_text().strip()


def get_attribute(page, selector, attribute):
    """Lấy giá trị thuộc tính của phần tử đầu tiên khớp selector."""
    element = page.locator(selector)
    if element.count() == 0:
        return None
    return element.first.get_attribute(attribute)


def parse_price(text):
    """'295.000đ / Hộp' -> 295000 (int). Trả về None nếu không có số."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text.split("/")[0])
    return int(digits) if digits else None


def wait_page_ready(page):
    """Chờ trang tải xong, sau đó chờ thêm cho mạng yên (nếu được)."""
    page.wait_for_load_state("load", timeout=PAGE_LOAD_TIMEOUT)
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
    except PWTimeout:
        pass  # site có script chạy liên tục thì bỏ qua, không coi là lỗi


def random_sleep(low, high):
    time.sleep(random.uniform(low, high))


# ======================================================================
# GIAI ĐOẠN 1: THU THẬP LINK SẢN PHẨM TỪ TRANG DANH MỤC
# ======================================================================
def collect_product_links(page, max_products=None):
    page.goto(CATEGORY_URL, timeout=PAGE_LOAD_TIMEOUT)
    wait_page_ready(page)
    page.locator(CARD_LINK).first.wait_for(timeout=ELEMENT_TIMEOUT)

    for _ in range(MAX_LOAD_MORE):
        current = page.locator(CARD_LINK).count() // 2  # mỗi thẻ có 2 link (ảnh + tên)
        print(f"  Đang có ~{current} sản phẩm trên trang")

        if max_products and current >= max_products:
            break

        # Nút "Xem thêm 124 sản phẩm" ở cuối danh sách
        load_more = page.locator(
            "#category-page__products-section button",
            has_text=re.compile(r"Xem thêm\s*\d+\s*sản phẩm"),
        )
        if load_more.count() == 0:
            print("  Hết nút 'Xem thêm' -> đã tải toàn bộ danh mục")
            break

        before = page.locator(CARD_LINK).count()
        load_more.first.scroll_into_view_if_needed()
        load_more.first.click()

        # Chờ đến khi số link tăng lên (dữ liệu mới đã render)
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
    # Chuẩn hoá URL tuyệt đối + loại trùng nhưng giữ thứ tự
    links = list(dict.fromkeys(urljoin(BASE_URL, h.strip()) for h in hrefs if h))

    return links[:max_products] if max_products else links


# ======================================================================
# GIAI ĐOẠN 2: CÀO CHI TIẾT MỘT SẢN PHẨM
# ======================================================================
def scrape_product(page, url):
    page.goto(url, timeout=PAGE_LOAD_TIMEOUT)
    wait_page_ready(page)
    page.locator('[data-test="product_name"]').first.wait_for(timeout=ELEMENT_TIMEOUT)

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
        # 1. Mở trình duyệt
        browser = p.chromium.launch(headless=HEADLESS)

        # 2. Tạo page và đặt thời gian chờ mặc định
        page = browser.new_page()
        page.set_default_timeout(ELEMENT_TIMEOUT)
        page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT)

        try:
            # 3. Thu thập link sản phẩm
            print("Bước 1: Thu thập link sản phẩm...")
            links = collect_product_links(page, MAX_PRODUCTS)
            print(f"-> Thu được {len(links)} link\n")

            # 4. Cào chi tiết từng sản phẩm
            print("Bước 2: Cào chi tiết từng sản phẩm...")
            for i, url in enumerate(links, start=1):
                try:
                    product = scrape_product(page, url)
                    print(f"[{i}/{len(links)}] OK  - {product['name']}")
                except Exception as e:
                    product = {"url": url, "error": str(e)[:200]}
                    print(f"[{i}/{len(links)}] LỖI - {url}")
                results.append(product)

                # Nghỉ ngẫu nhiên để tránh gửi request dồn dập
                random_sleep(DELAY_MIN, DELAY_MAX)

        except KeyboardInterrupt:
            print("\nNgười dùng dừng chương trình, đang lưu dữ liệu đã cào...")

        finally:
            # 5. Đóng trình duyệt và xuất Excel (kể cả khi lỗi giữa chừng)
            browser.close()
            if results:
                df = pd.DataFrame(results)
                df.to_excel(OUTPUT_FILE, index=False)
                ok = df["error"].isna().sum()
                print(f"\nĐã xuất {len(df)} dòng ({ok} thành công) ra {OUTPUT_FILE}")
            else:
                print("\nKhông có dữ liệu để xuất.")


if __name__ == "__main__":
    main()