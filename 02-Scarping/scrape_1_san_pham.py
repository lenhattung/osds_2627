# ============================================================
#  CÀO THÔNG TIN SẢN PHẨM NHÀ THUỐC LONG CHÂU - PLAYWRIGHT
#  Kết quả: file san_pham_long_chau.csv
# ============================================================
import json
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ---------- 1. CẤU HÌNH ----------
# Muốn cào sản phẩm khác: thêm URL vào danh sách này
DANH_SACH_URL = [
    "https://nhathuoclongchau.com.vn/thuc-pham-chuc-nang/enterogermina-baby-comfort-sanofi-hop-8-ml.html",
]
TEN_FILE_CSV = "san_pham_long_chau.csv"


# ---------- 2. HÀM LÀM SẠCH VĂN BẢN ----------
def lam_sach(html):
    """Biến đoạn HTML thành văn bản thuần, mỗi đoạn <p>/<li> một dòng."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    cac_doan = soup.find_all(["p", "li"])
    if not cac_doan:                       # HTML không có <p>/<li>
        return " ".join(soup.get_text().split())
    cac_dong = [" ".join(doan.get_text().split()) for doan in cac_doan]
    return "\n".join(dong for dong in cac_dong if dong)


# ---------- 3. HÀM LẤY KHỐI JSON TỪ TRANG ----------
def lay_json(trang, url):
    """Mở trang và đọc nội dung thẻ <script id="__NEXT_DATA__">."""
    trang.goto(url, wait_until="domcontentloaded", timeout=60000)
    chuoi_json = trang.locator("#__NEXT_DATA__").text_content()
    return json.loads(chuoi_json)


# ---------- 4. HÀM LẤY CÁC TRƯỜNG CẦN THIẾT ----------
def trich_xuat(du_lieu, url):
    page_props = du_lieu["props"]["pageProps"]
    sp = page_props["product"]                       # thông tin sản phẩm
    noi_dung = page_props.get("content") or {}       # công dụng, cách dùng...
    danh_gia = page_props.get("initReview") or {}
    binh_luan = page_props.get("initComment") or {}

    # Giá: lấy đơn vị bán mặc định (ví dụ "Hộp")
    ds_gia = sp.get("prices") or []
    gia = next((g for g in ds_gia if g.get("isSellDefault")), ds_gia[0] if ds_gia else {})

    # Khuyến mãi (có thể không có)
    ds_km = page_props.get("initPromotionPrices") or []
    km = ds_km[0] if ds_km else {}

    # Thành phần: "Tên hoạt chất (hàm lượng)"
    thanh_phan = [f'{tp.get("name")} ({tp.get("shortDescription")})' for tp in sp.get("ingredient") or []]

    # Hình ảnh: ảnh đại diện + các ảnh phụ
    hinh_chinh = (sp.get("primaryImage") or {}).get("url", "")
    hinh_phu = [h["url"] for h in sp.get("secondaryImages") or []]

    return {
        "url": url,
        "ma_san_pham": sp.get("sku"),
        "ten_san_pham": sp.get("webName"),
        "ten_chinh_hang": sp.get("officialProductName"),
        "thuong_hieu": sp.get("brand"),
        "xuat_xu_thuong_hieu": sp.get("brandOrigin"),
        "nuoc_san_xuat": sp.get("manufactor"),
        "nha_san_xuat": sp.get("producer"),
        "so_dang_ky": sp.get("registNum"),
        "dang_bao_che": sp.get("dosageForm"),
        "quy_cach": sp.get("specification"),
        "han_su_dung": sp.get("expirationDate"),
        "danh_muc": " > ".join(dm["name"] for dm in sp.get("categories") or []),
        "thanh_phan": " | ".join(thanh_phan),
        "don_vi_tinh": gia.get("measureUnitName"),
        "gia_goc": gia.get("price"),
        "gia_ban": km.get("finalPrice", gia.get("price")),
        "khuyen_mai": " | ".join(t["promotionTitle"] for t in km.get("promotionTags") or []),
        "diem_danh_gia": danh_gia.get("avgRating"),
        "so_danh_gia": danh_gia.get("total"),
        "so_binh_luan": binh_luan.get("total"),
        "hinh_dai_dien": hinh_chinh,
        "tat_ca_hinh": " | ".join([hinh_chinh] + hinh_phu),
        "mo_ta_ngan": lam_sach(sp.get("shortDescription")),
        "cong_dung": lam_sach(noi_dung.get("usage")),
        "cach_dung": lam_sach(noi_dung.get("dosage")),
        "tac_dung_phu": lam_sach(noi_dung.get("adverseEffect")),
        "luu_y": lam_sach(noi_dung.get("careful")),
        "bao_quan": lam_sach(noi_dung.get("preservation")),
        "mo_ta_chi_tiet": lam_sach(noi_dung.get("description")),
    }


# ---------- 5. CHƯƠNG TRÌNH CHÍNH ----------
def main():
    ket_qua = []
    with sync_playwright() as p:
        trinh_duyet = p.chromium.launch(headless=False)   # True = chạy ẩn
        trang = trinh_duyet.new_page()

        for url in DANH_SACH_URL:
            print("Đang cào:", url)
            try:
                du_lieu = lay_json(trang, url)
                san_pham = trich_xuat(du_lieu, url)
                ket_qua.append(san_pham)
                print("  -> OK:", san_pham["ten_san_pham"])
            except Exception as loi:
                print("  -> LỖI:", loi)
            trang.wait_for_timeout(3000)   # nghỉ 3 giây, tránh gửi yêu cầu dồn dập

        trinh_duyet.close()

    # Xuất CSV (utf-8-sig để Excel hiển thị đúng tiếng Việt)
    bang = pd.DataFrame(ket_qua)
    bang.to_csv(TEN_FILE_CSV, index=False, encoding="utf-8-sig")
    print(f"\nĐã lưu {len(bang)} sản phẩm vào {TEN_FILE_CSV}")


if __name__ == "__main__":
    main()
