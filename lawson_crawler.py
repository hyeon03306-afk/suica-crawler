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

# 🌟 사장님이 알려주신 로손 신상품 찐 타겟 URL
LAWSON_URL = "https://www.lawson.co.jp/recommend/new/list/1530516_5162.html"

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

def crawl_lawson():
    translator = GoogleTranslator(source='ja', target='ko')
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }
    
    print("[로손] 맞춤형 크롤링 시작...")
    lawson_data = []
    seen_titles = set()

    try:
        response = requests.get(LAWSON_URL, headers=headers, timeout=10)
        response.encoding = 'utf-8' # 글자 깨짐 방지
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 사장님이 주신 사진 기반: ul > li 구조 안의 상품 정보 탐색
            items = soup.select("ul.heightLineParent li, .recommend-list li, article, .item, .list li")
            
            for item in items:
                # 1. 제목 (p.ttl)
                title_tag = item.select_one("p.ttl, .ttl, .name")
                if not title_tag: continue
                
                raw_title = title_tag.text.strip()
                raw_title = re.sub(r'\s+', ' ', raw_title)
                
                if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles:
                    continue

                # 2. 개별 상세 링크 
                a_tag = item.select_one("a")
                item_href = a_tag.get('href') if a_tag else ""
                item_url = urljoin("https://www.lawson.co.jp", item_href) if item_href else ""

                # 3. 가격 (p.price)
                price_tag = item.select_one("p.price, .price")
                raw_price = price_tag.text.strip() if price_tag else ""

                # 4. 출시일 (p.date)
                date_tag = item.select_one("p.date, .date")
                raw_launch = date_tag.text.strip() if date_tag else "진행 중인 신상품"

                # 5. 칼로리 추출 🌟 (kcal 이라는 단어가 들어간 텍스트 찾기)
                raw_kcal = ""
                # item 안의 모든 일반 텍스트 문단(p)을 뒤져서 kcal을 찾습니다.
                for p_tag in item.find_all('p'):
                    if 'kcal' in p_tag.text.lower():
                        raw_kcal = p_tag.text.strip()
                        break
                
                # 로손은 기본적으로 전국 발매가 많아 디폴트값 지정
                raw_region = "전국 (일부 점포 제외)" 

                # 구글 번역 (밴 방지)
                try:
                    kr_title = translator.translate(raw_title)
                    kr_price = translator.translate(raw_price) if raw_price else ""
                    kr_launch = translator.translate(raw_launch) if raw_launch else ""
                    
                    # 칼로리는 숫자+영어 조합이 많아 굳이 번역 안 해도 됨, 지저분한 것만 정리
                    kr_kcal = raw_kcal.replace("当たり", " 당 ").replace("食", "식").replace("個入", "개입")
                    
                    time.sleep(0.5) 
                except:
                    kr_title, kr_price, kr_launch, kr_kcal = raw_title, raw_price, raw_launch, raw_kcal

                if not is_spam(kr_title):
                    lawson_data.append({
                        "category": "🏪 편의점",
                        "brand": "로손",
                        "title": kr_title,
                        "price": kr_price,
                        "date": kr_launch,
                        "region": raw_region,
                        "itemUrl": item_url,
                        "kcal": kr_kcal, # ⬅️ 🌟 칼로리 데이터 추가!
                        "week": "", 
                        "imageUrl": ""
                    })
                    seen_titles.add(raw_title)
                    print(f"  -> 수집됨: {kr_title} / {kr_kcal}")
                    
    except Exception as e:
        print(f"🚨 로손 에러: {e}")
        
    return lawson_data

if __name__ == "__main__":
    lawson_items = crawl_lawson()
    
    firebase_key_str = os.environ.get('FIREBASE_KEY')
    if firebase_key_str and lawson_items:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        db.collection("crawled_events").document("로손").set({"items": lawson_items})
        print(f"✅ 로손 파이어베이스 업데이트 성공! (총 {len(lawson_items)}개) 🚀")
    else:
        print("🚨 FIREBASE_KEY 에러 또는 수집된 데이터 없음")
