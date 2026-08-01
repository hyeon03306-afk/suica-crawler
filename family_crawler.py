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

# 🌟 사장님이 알려주신 패밀리마트 신상품 찐 타겟 URL
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
    
    print("[패밀리마트] 맞춤형 크롤링 시작...")
    family_data = []
    seen_titles = set()

    try:
        response = requests.get(FAMILY_URL, headers=headers, timeout=10)
        
        # 패밀리마트는 UTF-8 모범생 사이트! 깨짐 없이 바로 갑니다.
        response.encoding = 'utf-8' 
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 사장님 사진 기반: 정확한 덩어리 클래스 지정 (.ly-mod-layout-column)
            items = soup.select(".ly-mod-layout-column, .ly-goods-list-item")
            
            for item in items:
                # 1. 제목 (.ly-mod-info-title)
                title_tag = item.select_one(".ly-mod-info-title, .ly-goods-name")
                if not title_tag: continue
                
                raw_title = title_tag.text.strip()
                raw_title = re.sub(r'\s+', ' ', raw_title)
                
                if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles:
                    continue

                # 2. 상세 페이지 링크 
                a_tag = item.select_one("a")
                item_href = a_tag.get('href') if a_tag else ""
                item_url = urljoin("https://www.family.co.jp", item_href) if item_href else ""

                # 3. 가격 (.ly-mod-info-price)
                price_tag = item.select_one(".ly-mod-info-price, .ly-goods-price")
                raw_price = price_tag.text.strip() if price_tag else ""

                # 4. 출시일 (패밀리마트는 상단에 주간 날짜를 적어둬서 기본값으로 통일)
                raw_launch = "이번 주 신상품"

                # 5. 지역 (전국 통일)
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
                        "itemUrl": item_url, # ⬅️ 완벽하게 긁어온 상세 링크!
                        "kcal": "", # 패밀리마트 메인에는 칼로리 없음
                        "week": "", 
                        "imageUrl": ""
                    })
                    seen_titles.add(raw_title)
                    print(f"  -> 수집됨: {kr_title}")
                    
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
        
        # '패밀리마트' 문서에 차곡차곡 저장!
        db.collection("crawled_events").document("패밀리마트").set({"items": family_items})
        print(f"✅ 패밀리마트 파이어베이스 업데이트 성공! (총 {len(family_items)}개) 🚀")
    else:
        print("🚨 FIREBASE_KEY 에러 또는 수집된 데이터 없음")
