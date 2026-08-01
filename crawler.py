import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
import re
import time
from urllib.parse import urljoin

SEVEN_ELEVEN_URLS = [
    "https://www.sej.co.jp/products/a/thisweek/",
    "https://www.sej.co.jp/products/a/nextweek/"
]

TARGET_SITES = {
    "로손": "https://www.lawson.co.jp/recommend/index.html",
    "패밀리마트": "https://www.family.co.jp/campaign.html",
    "뉴데이즈": "https://retail.jr-cross.co.jp/newdays/product/" 
}

BLOCK_KEYWORDS = [
    "アルバイト", "パート", "募集", "採用", "求人", "店舗検索", "会社案内", "加盟店", 
    "お知らせ", "お問合せ", "サイトマップ", "アプリ", "SNS", "オーナー",
    "아르바이트", "파트타임", "모집", "채용", "구인", "점포", "가맹점", "회사", "공지사항", "문의"
]

def is_spam(text):
    for word in BLOCK_KEYWORDS:
        if word in text:
            return True
    return False

def smart_translate(text, cache_dict, deepl_key):
    if not text: return ""
    if text in cache_dict:
        return cache_dict[text]
    
    if deepl_key:
        try:
            url = "https://api-free.deepl.com/v2/translate"
            headers = {
                "Authorization": f"DeepL-Auth-Key {deepl_key}",
                "Content-Type": "application/json"
            }
            data = {"text": [text], "target_lang": "KO"}
            res = requests.post(url, headers=headers, json=data)
            
            if res.status_code == 200:
                translated = res.json()['translations'][0]['text']
                cache_dict[text] = translated 
                return translated
        except Exception as e:
            print(f"DeepL 번역 에러: {e}")
            
    return text 

def crawl_convenience_stores(db, deepl_key):
    cache_ref = db.collection("system").document("translation_cache")
    cache_doc = cache_ref.get()
    trans_cache = cache_doc.to_dict() if cache_doc.exists else {}
    initial_cache_size = len(trans_cache)

    all_store_data = {}
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }

    print(f"[세븐일레븐] 크롤링 시작... (현재 번역 노트에 {initial_cache_size}개 기억 중)")
    seven_data = []
    seen_seven_titles = set()

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
                    if is_spam(raw_title) or raw_title in seen_seven_titles: continue
                        
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
                        seen_seven_titles.add(raw_title)
        except Exception as e:
            print(f"🚨 세븐일레븐 에러: {e}")
            
    all_store_data["세븐일레븐"] = seven_data
    print(f"✅ 세븐일레븐: 총 {len(seven_data)}개 수집 완료")

    # 🚨 사장님 죄송합니다! 제가 아까 이 중요한 base_urls를 날려먹었습니다 ㅠㅠ
    base_urls = {
        "로손": "https://www.lawson.co.jp",
        "패밀리마트": "https://www.family.co.jp",
        "뉴데이즈": "https://retail.jr-cross.co.jp"
    }

    for brand_name, list_url in TARGET_SITES.items():
        print(f"[{brand_name}] 크롤링 시작...")
        parsed_data = []
        seen_titles = set()

        try:
            response = requests.get(list_url, headers=headers, timeout=10)
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.text, 'html.parser')
            main_content = soup.find('main') or soup.find(id='main') or soup.find(class_='main') or soup
            cards = main_content.select("article, .card, .item, .campaign-list li, .list li, li a, .box, .product-list li")
            if not cards: cards = main_content.select("a")

            for card in cards:
                title = ""
                title_tag = card.select_one("h2, h3, h4, .title, .name, p")
                if title_tag: title = title_tag.text.strip()
                elif card.name == 'a' and len(card.text.strip()) > 5: title = card.text.strip()
                title = re.sub(r'\s+', ' ', title).strip() 

                if not title or len(title) < 4 or title in seen_titles or is_spam(title): continue

                a_tag = card if card.name == 'a' else card.select_one("a")
                item_href = a_tag.get('href') if a_tag else ""
                item_url = urljoin(base_urls.get(brand_name, ""), item_href) if item_href else ""

                date_text = "이벤트 진행중"
                date_match = re.search(r'(\d{1,2}/\d{1,2}\s*\(.*?\))', title)
                if date_match: date_text = date_match.group(1) + " 부터"
                else:
                    date_tag = card.select_one(".date, time, .period")
                    if date_tag and any(char.isdigit() for char in date_tag.text): date_text = date_tag.text.strip()

                kr_title = smart_translate(title[:50], trans_cache, deepl_key)
                kr_date = smart_translate(date_text[:30], trans_cache, deepl_key) if date_text else ""
                time.sleep(0.1)

                if is_spam(kr_title): continue

                parsed_data.append({
                    "category": "🏪 편의점",
                    "brand": brand_name,
                    "title": kr_title,
                    "price": "",  
                    "date": kr_date,
                    "region": "", 
                    "itemUrl": item_url, 
                    "week": "", 
                    "imageUrl": ""
                })
                seen_titles.add(title)

            all_store_data[brand_name] = parsed_data
            print(f"✅ {brand_name}: 총 {len(parsed_data)}개 수집 완료")

        except Exception as e:
            print(f"🚨 {brand_name} 크롤링 에러: {e}")
            all_store_data[brand_name] = []

    if len(trans_cache) > initial_cache_size:
        cache_ref.set(trans_cache)
        print(f"✅ 번역 노트에 {len(trans_cache) - initial_cache_size}개의 새로운 단어가 추가로 기억되었습니다!")

    return all_store_data

if __name__ == "__main__":
    print("편의점 통합 크롤링 시작...")
    
    firebase_key_str = os.environ.get('FIREBASE_KEY')
    deepl_key = os.environ.get('DEEPL_KEY')
    
    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        
        data_map = crawl_convenience_stores(db, deepl_key)

        for brand, items in data_map.items():
            if items:
                db.collection("crawled_events").document(brand).set({"items": items})
        print("파이어베이스 업데이트 완료! 🚀")
    else:
        print("🚨 FIREBASE_KEY 에러")
