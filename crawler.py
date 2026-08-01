import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
import time
from urllib.parse import urljoin

SEVEN_ELEVEN_URLS = [
    "https://www.sej.co.jp/products/a/thisweek/",
    "https://www.sej.co.jp/products/a/nextweek/"
]

BLOCK_KEYWORDS = [
    "アルバイト", "パート", "募集", "採用", "求人", "店舗検索", "会社案内", "加盟店", 
    "お知らせ", "お問合せ", "サイトマップ", "アプリ", "SNS", "オーナー"
]

def is_spam(text):
    for word in BLOCK_KEYWORDS:
        if word in text: return True
    return False

def smart_translate(text, cache_dict, deepl_key):
    if not text: return ""
    if text in cache_dict: return cache_dict[text]
    
    if deepl_key:
        try:
            url = "https://api-free.deepl.com/v2/translate"
            headers = { "Authorization": f"DeepL-Auth-Key {deepl_key}", "Content-Type": "application/json" }
            data = {"text": [text], "target_lang": "KO"}
            res = requests.post(url, headers=headers, json=data)
            if res.status_code == 200:
                translated = res.json()['translations'][0]['text']
                cache_dict[text] = translated 
                return translated
        except Exception as e: print(f"DeepL 번역 에러: {e}")
    return text 

def crawl_seven_eleven(db, deepl_key):
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
    cache_ref = db.collection("system").document("translation_cache")
    cache_doc = cache_ref.get()
    trans_cache = cache_doc.to_dict() if cache_doc.exists else {}
    initial_cache_size = len(trans_cache)

    print(f"[세븐일레븐] 크롤링 시작... (현재 번역 노트에 {initial_cache_size}개 기억 중)")
    seven_data = []
    seen_titles = set()

    for url in SEVEN_ELEVEN_URLS:
        week_label = "이번주" if "thisweek" in url else "다음주"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.select(".list_inner .detail")
                
                for item in items:
                    title_tag = item.select_one(".item_ttl a")
                    if not title_tag: continue
                    raw_title = title_tag.text.strip()
                    if is_spam(raw_title) or raw_title in seen_titles: continue
                        
                    item_href = title_tag.get('href')
                    item_url = urljoin("https://www.sej.co.jp", item_href) if item_href else ""

                    price_tag = item.select_one(".item_price")
                    raw_price = price_tag.text.strip() if price_tag else ""
                    launch_tag = item.select_one(".item_launch")
                    raw_launch = launch_tag.text.strip() if launch_tag else ""
                    region_tag = item.select_one(".item_region")
                    raw_region = region_tag.text.strip().replace("販売地域：", "").replace("販売地域:", "").strip() if region_tag else ""

                    kr_title = smart_translate(raw_title, trans_cache, deepl_key)
                    kr_price = smart_translate(raw_price, trans_cache, deepl_key) if raw_price else ""
                    kr_launch = smart_translate(raw_launch, trans_cache, deepl_key) if raw_launch else ""
                    kr_region = smart_translate(raw_region, trans_cache, deepl_key) if raw_region else ""
                    time.sleep(0.1) 

                    if not is_spam(kr_title):
                        seven_data.append({
                            "category": "🏪 편의점",
                            "brand": "세븐일레븐",
                            "title": kr_title,
                            "price": kr_price,
                            "date": kr_launch,
                            "region": kr_region,
                            "itemUrl": item_url,
                            "week": week_label, 
                            "imageUrl": ""
                        })
                        seen_titles.add(raw_title)
        except Exception as e: print(f"🚨 세븐일레븐 에러: {e}")

    if len(trans_cache) > initial_cache_size:
        cache_ref.set(trans_cache)
        print(f"✅ 번역 노트 추가 완료!")

    return {"세븐일레븐": seven_data}

if __name__ == "__main__":
    firebase_key_str = os.environ.get('FIREBASE_KEY')
    deepl_key = os.environ.get('DEEPL_KEY')
    
    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps: firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        data_map = crawl_seven_eleven(db, deepl_key)
        for brand, items in data_map.items():
            if items: db.collection("crawled_events").document(brand).set({"items": items})
        print("✅ 세븐일레븐 파이어베이스 업데이트 완료!")
