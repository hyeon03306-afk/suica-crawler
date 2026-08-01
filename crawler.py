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

# 세븐일레븐은 이번주/다음주 신상품 페이지를 각각 타겟팅합니다.
TARGET_SITES = {
    "로손": "https://www.lawson.co.jp/recommend/index.html",
    "패밀리마트": "https://www.family.co.jp/campaign.html",
    "미니스톱": "https://www.ministop.co.jp/corporate/campaign/",
    "뉴데이즈": "https://retail.jr-cross.co.jp/newdays/product/" 
}

SEVEN_ELEVEN_URLS = [
    "https://www.sej.co.jp/products/a/thisweek/",
    "https://www.sej.co.jp/products/a/nextweek/"
]

BLOCK_KEYWORDS = [
    "アルバイト", "パート", "募集", "採用", "求人", "店舗検索", "会社案内", "加盟店", 
    "お知らせ", "お問合せ", "サイトマップ", "アプリ", "SNS", "オーナー",
    "아르바이트", "파트타임", "모집", "채용", "구인", "점포", "가맹점", "회사", "공지사항", "문의"
]

def is_spam(title_text):
    for block_word in BLOCK_KEYWORDS:
        if block_word in title_text:
            return True
    return False

def crawl_convenience_stores():
    translator = GoogleTranslator(source='ja', target='ko')
    all_store_data = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # ==========================================
    # 🌟 1. 세븐일레븐 신상품 전용 크롤링
    # ==========================================
    print("[세븐일레븐] 크롤링 시작...")
    seven_data = []
    seen_seven_titles = set()

    for url in SEVEN_ELEVEN_URLS:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # 엑스레이 사진 참고: .list_inner 안의 디테일을 뒤집니다.
                items = soup.select(".list_inner .detail")
                
                for item in items:
                    title_tag = item.select_one(".item_ttl a")
                    if not title_tag:
                        continue
                    
                    raw_title = title_tag.text.strip()
                    if is_spam(raw_title) or raw_title in seen_seven_titles:
                        continue
                        
                    # 가격, 날짜, 지역 추출
                    price_tag = item.select_one(".item_price")
                    price_text = price_tag.text.strip() if price_tag else ""
                    
                    launch_tag = item.select_one(".item_launch")
                    launch_text = launch_tag.text.strip() if launch_tag else ""
                    
                    region_tag = item.select_one(".item_region")
                    region_text = region_tag.text.strip() if region_tag else ""

                    # 깔끔하게 합치기 (예: "2026년 07월 28일 (화) 이후 순차 발매 | 지역: 홋카이도")
                    full_date_info = launch_text
                    if region_text:
                        full_date_info += f" | {region_text}"

                    try:
                        time.sleep(1.0)
                        kr_title = translator.translate(raw_title)
                        kr_price = translator.translate(price_text)
                        kr_date_info = translator.translate(full_date_info)
                    except:
                        kr_title = raw_title
                        kr_price = price_text
                        kr_date_info = full_date_info

                    # 최종 제목에 가격 합치기
                    final_title = f"{kr_title} ({kr_price})"
                    
                    if not is_spam(final_title):
                        seven_data.append({
                            "category": "🏪 편의점",
                            "brand": "세븐일레븐",
                            "title": final_title,
                            "date": kr_date_info,
                            "imageUrl": ""
                        })
                        seen_seven_titles.add(raw_title)

                    if len(seven_data) >= 15: # 세븐일레븐 15개 제한
                        break
        except Exception as e:
            print(f"🚨 세븐일레븐 에러: {e}")
            
    all_store_data["세븐일레븐"] = seven_data
    print(f"✅ 세븐일레븐: {len(seven_data)}개 수집 완료")

    # ==========================================
    # 🌟 2. 나머지 편의점 기존 방식 크롤링
    # ==========================================
    for brand_name, url in TARGET_SITES.items():
        print(f"[{brand_name}] 크롤링 시작...")
        parsed_data = []
        seen_titles = set()

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"⚠️ {brand_name} 접속 실패 (코드: {response.status_code})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            main_content = soup.find('main') or soup.find(id='main') or soup.find(class_='main') or soup

            cards = main_content.select("article, .card, .item, .campaign-list li, .list li, li a, .box, .product-list li")
            if not cards:
                cards = main_content.select("a")

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

                date_text = "이벤트 진행중"
                date_match = re.search(r'(\d{1,2}/\d{1,2}\s*\(.*?\))', title)
                if date_match:
                    date_text = date_match.group(1) + " 부터"
                else:
                    date_tag = card.select_one(".date, time, .period")
                    if date_tag and any(char.isdigit() for char in date_tag.text):
                        date_text = date_tag.text.strip()

                try:
                    time.sleep(1.0)
                    kr_title = translator.translate(title[:50])
                    kr_date = translator.translate(date_text[:30])
                except:
                    kr_title = title
                    kr_date = date_text

                if is_spam(kr_title):
                    continue

                parsed_data.append({
                    "category": "🏪 편의점",
                    "brand": brand_name,
                    "title": kr_title,
                    "date": kr_date,
                    "imageUrl": ""
                })
                seen_titles.add(title)

                if len(parsed_data) >= 15:
                    break

            all_store_data[brand_name] = parsed_data
            print(f"✅ {brand_name}: {len(parsed_data)}개 수집 완료")

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
