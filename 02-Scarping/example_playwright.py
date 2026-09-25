from playwright.sync_api import sync_playwright

url = "https://nhathuoclongchau.com.vn/thuc-pham-chuc-nang/vien-uong-ho-tro-cai-thien-suc-de-khang-cho-co-the-zincelite-vitamins-for-life-30-v.html"

with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page.goto(url)

    print(page.title())

    browser.close()