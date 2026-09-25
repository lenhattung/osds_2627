import json
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = "https://nhathuoclongchau.com.vn/thuc-pham-chuc-nang/enterogermina-baby-comfort-sanofi-hop-8-ml.html"

def txt(page, selector):
    """Trả về textContent của phần tử đầu tiên khớp selector, hoặc None nếu không có."""
    loc = page.locator(selector)
    if loc.count() == 0:
        return None
    return " ".join((loc.first.text_content() or "").split())

def html_to_text(s):
    """Chuyển đoạn HTML (trong JSON) thành văn bản thuần."""
    return BeautifulSoup(s or "", "lxml").get_text("\n", strip=True)

def scrape_dom(page):
    """Cách A: đọc trực tiếp từ giao diện (DOM)."""
    prod = {
        "ten":         txt(page, "[data-test='product_name']"),
        "sku":         txt(page, "[data-test-id='sku']"),
        "gia_ban":     txt(page, "[data-test='price']"),
        "gia_goc":     txt(page, "[data-test='strike_price'] p"),   # None nếu không giảm giá
        "don_vi":      txt(page, "[data-test='unit']"),
        "thuong_hieu": txt(page, "a[href^='/thuong-hieu/']"),
        "xuat_xu":     txt(page, "xpath=//div[span[contains(.,'Thương hiệu')]]/preceding-sibling::div[1]//span"),
        "hinh_anh":    page.locator("meta[property='og:image']").get_attribute("content"),
        "diem_danh_gia": txt(page, "xpath=//span[@data-test-id='sku']/following-sibling::span[contains(@class,'inline-flex')]"),
    }
 
    # Số đánh giá và số bình luận: 2 span có thể bấm được, đứng sau SKU
    counts = page.locator("xpath=//span[@data-test-id='sku']/following-sibling::span[contains(@class,'cursor-pointer')]")
    if counts.count() >= 2:
        prod["so_danh_gia"] = counts.nth(0).text_content().strip()
        prod["so_binh_luan"] = counts.nth(1).text_content().strip()
 
    # Bấm "Xem tất cả thông tin" để hiện các trường bị ẩn
    btn = page.get_by_text("Xem tất cả thông tin", exact=True)
    if btn.count():
        btn.first.scroll_into_view_if_needed()
        btn.first.click()
        page.wait_for_timeout(1000)   # chờ nội dung mở rộng
 
    # Các dòng "nhãn : giá trị"
    labels = ["Tên chính hãng", "Số đăng ký", "Thành phần", "Dạng bào chế", "Quy cách",
              "Danh mục", "Nhà sản xuất", "Nước sản xuất", "Hạn sử dụng"]
    prod["thong_tin_khac"] = {
        lb: v for lb in labels
        if (v := txt(page, f"xpath=//div[p[normalize-space()='{lb}']]/following-sibling::div[1]"))
    }
 
    # Mô tả: text_content() lấy cả phần bị khung overflow che mất
    prod["mo_ta"] = {
        cls: page.locator(f"#content-wrapper div.{cls}").first.text_content().strip()
        for cls in ["description", "usage", "dosage", "careful", "preservation", "adverseEffect"]
        if page.locator(f"#content-wrapper div.{cls}").count()
    }
    return prod
 
 
def scrape_nextdata(page):
    """Cách B: đọc khối JSON __NEXT_DATA__ mà Next.js nhúng sẵn."""
    data = page.evaluate("() => window.__NEXT_DATA__")
    # Dự phòng nếu biến window không tồn tại:
    # data = json.loads(page.locator("#__NEXT_DATA__").text_content())
    props = data["props"]["pageProps"]
    p = props["product"]
    content = props.get("content") or {}
    promo = (props.get("initPromotionPrices") or [{}])[0]
    review = props.get("initReview") or {}
    price0 = next((x for x in p["prices"] if x.get("isSellDefault")), p["prices"][0])
 
    return {
        "ten": p["webName"],
        "ten_chinh_hang": p.get("officialProductName"),
        "sku": p["sku"],
        "thuong_hieu": p.get("brand"),
        "xuat_xu_thuong_hieu": p.get("brandOrigin"),
        "nuoc_san_xuat": p.get("manufactor"),
        "nha_san_xuat": p.get("producer"),
        "so_dang_ky": p.get("registNum"),
        "dang_bao_che": p.get("dosageForm"),
        "quy_cach": p.get("specification"),
        "han_su_dung": p.get("expirationDate"),
        "danh_muc": " > ".join(c["name"] for c in p.get("categories", [])),
        "thanh_phan": [f'{i["name"]} ({i["shortDescription"]})' for i in p.get("ingredient", [])],
        "don_vi": price0["measureUnitName"],
        "gia_goc": price0["price"],
        "gia_ban": promo.get("finalPrice", price0["price"]),   # không có KM thì bằng giá gốc
        "khuyen_mai": [t["promotionTitle"] for t in promo.get("promotionTags", [])],
        "diem_danh_gia": review.get("avgRating"),
        "so_danh_gia": review.get("total"),
        "so_binh_luan": (props.get("initComment") or {}).get("total"),
        "hinh_anh": [p["primaryImage"]["url"]] + [i["url"] for i in p.get("secondaryImages", [])],
        "cong_dung": html_to_text(content.get("usage")),
        "cach_dung": html_to_text(content.get("dosage")),
        "luu_y": html_to_text(content.get("careful")),
        "bao_quan": html_to_text(content.get("preservation")),
    }
 
 
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)   # đổi thành True khi chạy thật
        context = browser.new_context(locale="vi-VN", viewport={"width": 1400, "height": 1000})
        page = context.new_page()
 
        # Chặn ảnh, font, video để tải nhanh hơn (không ảnh hưởng dữ liệu cần lấy)
        page.route("**/*", lambda r: r.abort()
                   if r.request.resource_type in ("image", "font", "media") else r.continue_())
 
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        try:
            page.locator("[data-test='product_name']").wait_for(timeout=15000)
        except PWTimeout:
            print("Không tìm thấy tên sản phẩm, có thể trang bị chặn hoặc đổi cấu trúc.")
            browser.close()
            return
 
        result = {
            "url": URL,
            "dom": scrape_dom(page),
            "nextdata": scrape_nextdata(page),
        }
        browser.close()
 
    with open("product_playwright.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
 
 
if __name__ == "__main__":
    main()

