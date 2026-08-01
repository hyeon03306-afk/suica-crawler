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

# 🌟 로손 신상품 메인 로비 (여기서 봇이 최신 주소를 스스로 찾아냅니다!)
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

# 🌟 최신 신상품 주소 자동 탐지기
def get_latest_lawson_url():
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
    try:
        res = requests.get(LAWSON_BASE_NEW_URL, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 8/4 발매, 7/28 발매 등 탭에서 가장 첫 번째(최신) 링크를 찾습니다.
        for a_tag in soup.find_all('a', href=True):
            if '/recommend/new/list/' in a_tag['href']:
                latest_url = urljoin("https://www.lawson.co.jp", a_tag['href'])
                print(f"[자동 탐지] 이번 주 로손 최신 주소 발견: {latest_url}")
                return latest_url
                
        # 만약 못 찾으면 사장님이 주셨던 기본 주소(또는 메인 로비)로 돌아갑니다.
        print("[자동 탐지] 최신 링크를 찾지 못해 기본 로비로 접속합니다.")
        return LAWSON_BASE_NEW_URL
    except Exception as e:
        print(f"🚨 주소 탐지 에러: {e}")
        return LAWSON_BASE_NEW_URL

def crawl_lawson():
    translator = GoogleTranslator(source='ja', target='ko')
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }
    
    # 봇이 알아서 최신 타겟 주소를 장전합니다!
    target_url = get_latest_lawson_url()
    
    print(f"[로손] 맞춤형 크롤링 시작... ({target_url})")
    lawson_data = []
    seen_titles = set()

    try:
        response = requests.get(target_url, headers=headers, timeout=10)
        response.encoding = 'utf-8' 
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            items = soup.select("ul.heightLineParent li, .recommend-list li, article, .item, .list li")
            
            for item in items:
                title_tag = item.select_one("p.ttl, .ttl, .name")
                if not title_tag: continue
                
                raw_title = title_tag.text.strip()
                raw_title = re.sub(r'\s+', ' ', raw_title)
                
                if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles:
                    continue

                # 💡 개별 상품 상세 링크 (누르면 바로 넘어가는 그 주소!)
                a_tag = item.select_one("a")
                item_href = a_tag.get('href') if a_tag else ""
                item_url = urljoin("https://www.lawson.co.jp", item_href) if item_href else ""

                price_tag = item.select_one("p.price, .price")
                raw_price = price_tag.text.strip() if price_tag else ""

                date_tag = item.select_one("p.date, .date")
                raw_launch = date_tag.text.strip() if date_tag else "이번 주 신상품"

                raw_kcal = ""
                for p_tag in item.find_all('p'):
                    if 'kcal' in p_tag.text.lower():
                        raw_kcal = p_tag.text.strip()
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
                        "itemUrl": item_url, # ⬅️ 안드로이드 앱이 이걸 받아서 쏩니다!
                        "kcal": kr_kcal, 
                        "week": "이번주", # 탭 분류용
                        "imageUrl": ""
                    })
                    seen_titles.add(raw_title)
                    
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
