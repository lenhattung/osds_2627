# kiem_tra_robots.py
from urllib import robotparser

rp = robotparser.RobotFileParser()

rp.set_url("https://nhathuoclongchau.com.vn/robots.txt")
rp.read()
url_thu = "https://nhathuoclongchau.com.vn/thuc-pham-chuc-nang/vitaminkhoang-chat"

print("Duoc phep thu thap:", rp.can_fetch("*", url_thu))
print("Crawl-delay:", rp.crawl_delay("*")) 
print("Sitemap:", rp.site_maps()) 