from playwright.sync_api import sync_playwright
import pandas as pd


URL = "https://nhathuoclongchau.com.vn/thuc-pham-chuc-nang/vien-uong-ho-tro-cai-thien-suc-de-khang-cho-co-the-zincelite-vitamins-for-life-30-v.html"


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


with sync_playwright() as p:

    # 1. Mở trình duyệt
    browser = p.chromium.launch(headless=False)

    # 2. Tạo page
    page = browser.new_page()

    # 3. Truy cập website
    page.goto(URL)

    # 4. Chờ trang tải
    page.wait_for_load_state("domcontentloaded")

    # 5. Cào dữ liệu
    product = {
        "url": page.url,

        "name": get_text(
            page,
            '[data-test="product_name"]'
        ),

        "sku": get_text(
            page,
            '[data-test-id="sku"]'
        ),

        "price": get_text(
            page,
            '[data-test="price"]'
        ),

        "original_price": get_text(
            page,
            '[data-test="strike_price"]'
        ),

        "image": get_attribute(
            page,
            'meta[property="og:image"]',
            "content"
        )
    }

    # 6. In dữ liệu ra màn hình
    print(product)

    # 7. Chuyển dictionary thành DataFrame
    df = pd.DataFrame([product])

    # 8. Xuất Excel
    df.to_excel(
        "product.xlsx",
        index=False
    )

    print("\nĐã xuất dữ liệu ra file product.xlsx")

    # 9. Đóng trình duyệt
    browser.close()