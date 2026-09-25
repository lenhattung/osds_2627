# tien_ich.py - ham dung chung: tao bang, doc URL, trich xuat, ghi ket qua
import re
import sqlite3
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from cau_hinh import DB, SO_URL

def ket_noi():
    """Ket noi toi CSDL SQLite"""
    try:
        conn = sqlite3.connect(DB)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                danh_muc TEXT,
            );

            CREATE TABLE IF NOT EXISTS ket_qua (
                cong_cu TEXT, 
                lan INTEGER, 
                url TEXT, 
                trang_thai TEXT,
                ten TEXT, 
                gia INTEGER, 
                don_vi TEXT, 
                thuong_hieu TEXT, 
                so_dang_ky TEXT,
                thoi_gian_xu_ly REAL, 
                thoi_diem TEXT,
                PRIMARY KEY (cong_cu, lan, url)
            );
            CREATE TABLE IF NOT EXISTS lan_chay (
                cong_cu TEXT, 
                lan INTEGER, 
                so_url INTEGER, 
                so_trang_ok INTEGER,
                tong_thoi_gian REAL, 
                thoi_gian_xu_ly REAL, 
                ram_dinh_mb REAL,
                thoi_diem TEXT);
     """);
         
        return conn
    except sqlite3.Error as e:
        print("Loi ket noi CSDL:", e)
        sys.exit(1)

