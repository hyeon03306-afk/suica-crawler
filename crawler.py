import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import json
import re
import time
from deep_translator import GoogleTranslator
from urllib.parse import urljoin  # 🌟 쪼개진 링크를 완전한 주소로 합쳐주는 마법의 도구!

SEVEN_ELEVEN_URLS = [
    "https://www.sej.co.jp/products/a/thisweek/",
    "https://www.sej.co.jp/products/a/nextweek/"
]

TARGET_SITES = {
    "로손": "https://www.lawson.co.jp/recommend/index.html",
    "패밀리마트": "https://www.family.co.jp/campaign.html",
    "미니스톱": "https://www.ministop.co.jp/corporate/campaign/",
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

def crawl_convenience_stores():
    translator = GoogleTranslator(source='ja', target='ko')
    all_store_data = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # ==========================================
    # 🌟 1. 세븐일레븐 '신상품' 싹쓸이 정밀 분석
    # ==========================================
    print("[세븐일레븐] 크롤링 시작...")
    seven_data = []
    seen_seven_titles = set()

    for url in SEVEN_ELEVEN_URLS:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                items = soup.select(".list_inner .detail")
                
                for item in items:
                    title_tag = item.select_one(".item_ttl a")
                    if not title_tag:
                        continue
                    
                    raw_title = title_tag.text.strip()
                    if is_spam(raw_title) or raw_title in seen_seven_titles:
                        continue
                        
                    # 💡 제품 전용 상세 링크 추출 및 합체!
                    item_href = title_tag.get('href')
                    item_url = urljoin("https://www.sej.co.jp", item_href) if item_href else ""

                    price_tag = item.select_one(".item_price")
                    raw_price = price_tag.text.strip() if price_tag else ""
                    
                    launch_tag = item.select_one(".item_launch")
                    raw_launch = launch_tag.text.strip() if launch_tag else ""
                    
                    region_tag = item.select_one(".item_region")
                    raw_region = region_tag.text.strip().replace("販売地域：", "").replace("販売地域:", "").strip() if region_tag else ""

                    try:
                        kr_title = translator.translate(raw_title)
                        kr_price = translator.translate(raw_price) if raw_price else ""
                        kr_launch = translator.translate(raw_launch) if raw_launch else ""
                        kr_region = translator.translate(raw_region) if raw_region else ""
                        time.sleep(0.5) 
                    except:
                        kr_title, kr_price, kr_launch, kr_region = raw_title, raw_price, raw_launch, raw_region

                    if not is_spam(kr_title):
                        seven_data.append({
                            "category": "🏪 편의점",
                            "brand": "세븐일레븐",
                            "title": kr_title,
                            "price": kr_price,
                            "date": kr_launch,
                            "region": kr_region,
                            "itemUrl": item_url, # ⬅️ 개별 상품 링크 저장!
                            "imageUrl": ""
                        })
                        seen_seven_titles.add(raw_title)
                        
        except Exception as e:
            print(f"🚨 세븐일레븐 에러: {e}")
            
    all_store_data["세븐일레븐"] = seven_data
    print(f"✅ 세븐일레븐: 총 {len(seven_data)}개 수집 완료")

    # ==========================================
    # 🌟 2. 나머지 편의점
    # ==========================================
    base_urls = {
        "로손": "https://www.lawson.co.jp",
        "패밀리마트": "https://www.family.co.jp",
        "미니스톱": "https://www.ministop.co.jp",
        "뉴데이즈": "https://retail.jr-cross.co.jp"
    }

    for brand_name, list_url in TARGET_SITES.items():
        print(f"[{brand_name}] 크롤링 시작...")
        parsed_data = []
        seen_titles = set()

        try:
            response = requests.get(list_url, headers=headers, timeout=10)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            main_content = soup.find('main') or soup.find(id='main') or soup.find(class_='main') or soup
            cards = main_content.select("article, .card, .item, .campaign-list li, .list li, li a, .box, .product-list li")
            if not cards: cards = main_content.select("a")

            for card in cards:
                title = ""
                title_tag = card.select_one("h2, h3, h4, .title, .name, p")
                if title_tag:
                    title = title_tag.text.strip()
                elif card.name == 'a' and len(card.text.strip()) > 5:
                    title = card.text.strip()
                title = re.sub(r'\s+', ' ', title).strip() 

                if not title or len(title) < 4 or title in seen_titles or is_spam(title):
                    continue

                # 💡 개별 상품 링크 추출 (있으면 가져오기!)
                a_tag = card if card.name == 'a' else card.select_one("a")
                item_href = a_tag.get('href') if a_tag else ""
                item_url = urljoin(base_urls.get(brand_name, ""), item_href) if item_href else ""

                date_text = "이벤트 진행중"
                date_match = re.search(r'(\d{1,2}/\d{1,2}\s*\(.*?\))', title)
                if date_match: date_text = date_match.group(1) + " 부터"
                else:
                    date_tag = card.select_one(".date, time, .period")
                    if date_tag and any(char.isdigit() for char in date_tag.text): date_text = date_tag.text.strip()

                try:
                    kr_title = translator.translate(title[:50])
                    kr_date = translator.translate(date_text[:30])
                    time.sleep(0.5)
                except:
                    kr_title, kr_date = title, date_text

                if is_spam(kr_title): continue

                parsed_data.append({
                    "category": "🏪 편의점",
                    "brand": brand_name,
                    "title": kr_title,
                    "price": "",  
                    "date": kr_date,
                    "region": "", 
                    "itemUrl": item_url, # ⬅️ 개별 상품 링크 저장!
                    "imageUrl": ""
                })
                seen_titles.add(title)

            all_store_data[brand_name] = parsed_data
            print(f"✅ {brand_name}: 총 {len(parsed_data)}개 수집 완료")

        except Exception as e:
            print(f"🚨 {brand_name} 크롤링 중 에러 발생: {e}")
            all_store_data[brand_name] = []

    return all_store_data

if __name__ == "__main__":
    print("편의점 통합 크롤링 및 번역 시작...")
    data_map = crawl_convenience_stores()

    firebase_key_str = os.environ.get('FIREBASE_KEY')
    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()

        for brand, items in data_map.items():
            if items:
                db.collection("crawled_events").document(brand).set({"items": items})
        
        print("모든 편의점 파이어베이스 업데이트 완벽 성공! 🚀")
    else:
        print("🚨 FIREBASE_KEY를 찾을 수 없습니다.")
