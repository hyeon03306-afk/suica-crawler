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
from urllib.parse import urljoin

# 패밀리마트 신상품 리스트 타겟 URL
FAMILY_URL = "https://www.family.co.jp/goods/newgoods.html"

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

def crawl_family_mart():
    translator = GoogleTranslator(source='ja', target='ko')
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }
    
    print("[패밀리마트] 정밀 타격 크롤링 시작...")
    family_data = []
    seen_titles = set()

    try:
        response = requests.get(FAMILY_URL, headers=headers, timeout=10)
        response.encoding = 'utf-8' 
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 🌟 수정 포인트 1: 상품을 감싸는 가장 정확한 컨테이너 'div.ly-goods-list-item'만 찾습니다.
            items = soup.select(".ly-goods-list-item")
            
            for item in items:
                # 1. 제목 (패밀리마트는 항상 h3 클래스로 제품명을 감쌈)
                title_tag = item.find('h3', class_='ly-goods-list-title')
                if not title_tag: continue
                
                raw_title = title_tag.text.strip()
                raw_title = re.sub(r'\s+', ' ', raw_title)
                
                if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles:
                    continue
                
                # 🚫 '영어'라는 단어가 단독으로 들어오는 찌꺼기 차단
                if raw_title == "영어" or raw_title == "英語":
                    continue

                # 2. 상세 페이지 링크 (a 태그)
                a_tag = item.find('a', href=True)
                item_href = a_tag['href'] if a_tag else ""
                item_url = urljoin("https://www.family.co.jp", item_href) if item_href else ""

                # 3. 가격 (div.ly-goods-list-price 안의 텍스트)
                price_tag = item.find('div', class_='ly-goods-list-price')
                raw_price = price_tag.text.strip() if price_tag else ""
                # 패밀리마트 가격 텍스트 깔끔하게 정리 (예: 156円（税込168円） -> 156円 (税込168円))
                raw_price = raw_price.replace('（', ' (').replace('）', ')')

                # 4. 출시일 및 지역 고정
                raw_launch = "이번 주 신상품"
                raw_region = "전국 (일부 점포 제외)" 

                try:
                    kr_title = translator.translate(raw_title)
                    kr_price = translator.translate(raw_price) if raw_price else ""
                    time.sleep(0.5) 
                except:
                    kr_title, kr_price = raw_title, raw_price

                if not is_spam(kr_title):
                    family_data.append({
                        "category": "🏪 편의점",
                        "brand": "패밀리마트",
                        "title": kr_title,
                        "price": kr_price,
                        "date": raw_launch,
                        "region": raw_region,
                        "itemUrl": item_url,
                        "kcal": "", 
                        "week": "", # 패밀리마트는 주간 구분이 모호하여 공란
                        "imageUrl": ""
                    })
                    seen_titles.add(raw_title)
                    print(f"  -> 수집됨: {kr_title} / {kr_price}")
                    
    except Exception as e:
        print(f"🚨 패밀리마트 에러: {e}")
        
    return family_data

if __name__ == "__main__":
    family_items = crawl_family_mart()
    
    firebase_key_str = os.environ.get('FIREBASE_KEY')
    if firebase_key_str and family_items:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        db.collection("crawled_events").document("패밀리마트").set({"items": family_items})
        print(f"✅ 패밀리마트 파이어베이스 업데이트 성공! (총 {len(family_items)}개) 🚀")
    else:
        print("🚨 FIREBASE_KEY 에러 또는 수집된 데이터 없음")
