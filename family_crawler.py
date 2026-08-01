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

# 🌟 패밀리마트 신상품 리스트 URL
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
    
    print("[패밀리마트] 엑스레이 기반 정밀 크롤링 시작...")
    family_data = []
    seen_titles = set()

    try:
        response = requests.get(FAMILY_URL, headers=headers, timeout=10)
        response.encoding = 'utf-8' 
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 🌟 사장님이 주신 사진의 진짜 뼈대: ly-mod-infoset3 (또는 4)
            items = soup.select(".ly-mod-infoset3, .ly-mod-infoset4")
            
            for item in items:
                # 1. 상세 페이지 링크 (a 태그)
                a_tag = item.find('a', href=True)
                if not a_tag: continue
                
                item_href = a_tag['href']
                item_url = urljoin("https://www.family.co.jp", item_href)

                # 2. 제목 (클래스 이름이 -ttl 로 끝나는 태그)
                title_tag = item.select_one('[class$="-ttl"]')
                raw_title = title_tag.text.strip() if title_tag else ""
                
                # 🛠️ 이중 안전장치: 만약 클래스 이름이 달라서 못 찾았을 경우 텍스트만 강제 추출
                if not raw_title:
                    txt_box = item.select_one('[class$="-txt"]')
                    if txt_box:
                        texts = [t.strip() for t in txt_box.stripped_strings if t.strip()]
                        if len(texts) > 1:
                            raw_title = texts[1] # [0]은 카테고리(おむすび), [1]이 진짜 제목(もち麦 ごまわかめ)

                raw_title = re.sub(r'\s+', ' ', raw_title)
                
                if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles:
                    continue

                # 3. 가격 (클래스 이름이 -price 로 끝나는 태그)
                price_tag = item.select_one('[class$="-price"]')
                raw_price = price_tag.text.strip() if price_tag else ""
                
                # 🛠️ 이중 안전장치: 못 찾았을 경우 '円'이 들어간 문장 억지로 찾기
                if not raw_price:
                    for p in item.find_all(['p', 'div', 'span']):
                        if '円' in p.text and '税込' in p.text:
                            raw_price = p.text.strip()
                            break

                raw_price = raw_price.replace('（', ' (').replace('）', ')')

                # 4. 고정 정보
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
                        "week": "이번주",
                        "imageUrl": ""
                    })
                    seen_titles.add(raw_title)
                    print(f"  -> 정상 수집됨: {kr_title} / {kr_price}")
                    
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
