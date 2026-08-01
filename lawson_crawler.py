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

LAWSON_BASE_NEW_URL = "https://www.lawson.co.jp/recommend/new/"

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

def get_latest_lawson_url():
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
    try:
        res = requests.get(LAWSON_BASE_NEW_URL, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for a_tag in soup.find_all('a', href=True):
            if '/recommend/new/list/' in a_tag['href']:
                latest_url = urljoin("https://www.lawson.co.jp", a_tag['href'])
                print(f"[자동 탐지] 이번 주 로손 최신 주소 발견: {latest_url}")
                return latest_url
                
        return LAWSON_BASE_NEW_URL
    except Exception as e:
        print(f"🚨 주소 탐지 에러: {e}")
        return LAWSON_BASE_NEW_URL

def crawl_lawson():
    translator = GoogleTranslator(source='ja', target='ko')
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }
    
    target_url = get_latest_lawson_url()
    print(f"[로손] 맞춤형 크롤링 시작... ({target_url})")
    lawson_data = []
    seen_titles = set()

    try:
        response = requests.get(target_url, headers=headers, timeout=10)
        
        # 🌟 원인 분석 적용: 찌그러진 바이트를 바르게 정렬하는 세탁기 로직
        response.encoding = 'utf-8'
        raw_html = response.text
        
        # BeautifulSoup 파싱 시 인코딩 간섭 원천 차단
        soup = BeautifulSoup(raw_html, 'html.parser')
        items = soup.select("ul.heightLineParent li, .recommend-list li, article, .item, .list li")
        
        for item in items:
            title_tag = item.select_one("p.ttl, .ttl, .name")
            if not title_tag: continue
            
            # 🌟 텍스트를 뽑자마자 바이트 깨짐 현상을 강제로 바로잡는 정제 과정
            raw_title = title_tag.text.encode('latin1', errors='ignore').decode('utf-8', errors='ignore')
            raw_title = re.sub(r'\s+', ' ', raw_title).strip()
            
            if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles:
                continue

            a_tag = item.select_one("a")
            item_href = a_tag.get('href') if a_tag else ""
            item_url = urljoin("https://www.lawson.co.jp", item_href) if item_href else ""

            price_tag = item.select_one("p.price, .price")
            raw_price = price_tag.text.encode('latin1', errors='ignore').decode('utf-8', errors='ignore').strip() if price_tag else ""

            date_tag = item.select_one("p.date, .date")
            raw_launch = date_tag.text.encode('latin1', errors='ignore').decode('utf-8', errors='ignore').strip() if date_tag else "이번 주 신상품"

            raw_kcal = ""
            for p_tag in item.find_all('p'):
                p_text = p_tag.text.encode('latin1', errors='ignore').decode('utf-8', errors='ignore')
                if 'kcal' in p_text.lower():
                    raw_kcal = p_text.strip()
                    break
            
            raw_region = "전국 (일부 점포 제외)" 

            try:
                kr_title = translator.translate(raw_title)
                kr_price = translator.translate(raw_price) if raw_price else ""
                kr_launch = translator.translate(raw_launch) if raw_launch else ""
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
                    "kcal": kr_kcal, 
                    "week": "이번주", 
                    "imageUrl": ""
                })
                seen_titles.add(raw_title)
                print(f"  -> 정상 수집됨: {kr_title} / {kr_kcal}")
                
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
