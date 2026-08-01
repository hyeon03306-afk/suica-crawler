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

FAMILY_URL = "https://www.family.co.jp/goods/newgoods.html"

BLOCK_KEYWORDS = [
    "アルバイト", "パート", "募集", "採用", "求人", "店舗検索", "会社案内", "加盟店", 
    "お知らせ", "お問合せ", "サイトマップ", "アプリ", "SNS", "オーナー"
]

def is_spam(text):
    for word in BLOCK_KEYWORDS:
        if word in text:
            return True
    return False

# 🧠 똑똑한 하이브리드 번역기 (DeepL + 파이어베이스 기억력)
def smart_translate(text, cache_dict, deepl_key):
    if not text: return ""
    
    # 1. 뇌(캐시) 검색: 이미 번역해 본 단어면 노트에서 바로 꺼내 씀! (API 0원 소모)
    if text in cache_dict:
        return cache_dict[text]
    
    # 2. 모르는 단어면 DeepL에 물어봄!
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
                cache_dict[text] = translated # 💡 다음에 또 안 물어보도록 뇌(캐시)에 저장!
                return translated
        except Exception as e:
            print(f"DeepL 번역 에러: {e}")
            
    return text # 에러 시 원본 반환

def crawl_family_mart(db, deepl_key):
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
    
    # 🧠 파이어베이스에서 기존 번역 노트(캐시) 불러오기
    cache_ref = db.collection("system").document("translation_cache")
    cache_doc = cache_ref.get()
    trans_cache = cache_doc.to_dict() if cache_doc.exists else {}
    initial_cache_size = len(trans_cache)

    print(f"[패밀리마트] 엑스레이 크롤링 시작... (현재 번역 노트에 {initial_cache_size}개 기억 중)")
    family_data = []
    seen_titles = set()

    try:
        response = requests.get(FAMILY_URL, headers=headers, timeout=10)
        response.encoding = 'utf-8' 
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select(".ly-mod-infoset3, .ly-mod-infoset4")
            
            for item in items:
                a_tag = item.find('a', href=True)
                if not a_tag: continue
                item_href = a_tag['href']
                item_url = urljoin("https://www.family.co.jp", item_href)

                title_tag = item.select_one('[class$="-ttl"]')
                raw_title = title_tag.text.strip() if title_tag else ""
                
                if not raw_title:
                    txt_box = item.select_one('[class$="-txt"]')
                    if txt_box:
                        texts = [t.strip() for t in txt_box.stripped_strings if t.strip()]
                        if len(texts) > 1:
                            raw_title = texts[1] 

                raw_title = re.sub(r'\s+', ' ', raw_title)
                if not raw_title or len(raw_title) < 2 or is_spam(raw_title) or raw_title in seen_titles:
                    continue

                price_tag = item.select_one('[class$="-price"]')
                raw_price = price_tag.text.strip() if price_tag else ""
                
                if not raw_price:
                    for p in item.find_all(['p', 'div', 'span']):
                        if '円' in p.text and '税込' in p.text:
                            raw_price = p.text.strip()
                            break
                raw_price = raw_price.replace('（', ' (').replace('）', ')')

                raw_launch = "이번 주 신상품"
                raw_region = "전국 (일부 점포 제외)" 

                # 🧠 여기서 똑똑한 하이브리드 번역기 작동!
                kr_title = smart_translate(raw_title, trans_cache, deepl_key)
                kr_price = smart_translate(raw_price, trans_cache, deepl_key) if raw_price else ""
                time.sleep(0.1) 

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
                    
        # 🧠 크롤링이 끝나면 새로 추가된 번역 단어들을 파이어베이스 노트에 업데이트!
        if len(trans_cache) > initial_cache_size:
            cache_ref.set(trans_cache)
            print(f"✅ 번역 노트에 {len(trans_cache) - initial_cache_size}개의 새로운 단어가 추가로 기억되었습니다!")

    except Exception as e:
        print(f"🚨 패밀리마트 에러: {e}")
        
    return family_data

if __name__ == "__main__":
    firebase_key_str = os.environ.get('FIREBASE_KEY')
    deepl_key = os.environ.get('DEEPL_KEY')
    
    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        family_items = crawl_family_mart(db, deepl_key)
        
        if family_items:
            db.collection("crawled_events").document("패밀리마트").set({"items": family_items})
            print(f"✅ 패밀리마트 업데이트 성공! (총 {len(family_items)}개) 🚀")
        else:
            print("🚨 수집된 데이터 없음")
    else:
        print("🚨 FIREBASE_KEY 에러")
