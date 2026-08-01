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

# 🌟 사장님이 픽해주신 잘 작동하는 고정 URL!
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

# 🧠 똑똑한 하이브리드 번역기 (DeepL + 파이어베이스 기억력)
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

# 💡 DB와 열쇠를 받도록 함수 수정
def crawl_lawson(db, deepl_key):
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }
    
    # 🧠 파이어베이스에서 기존 번역 노트(캐시) 불러오기
    cache_ref = db.collection("system").document("translation_cache")
    cache_doc = cache_ref.get()
    trans_cache = cache_doc.to_dict() if cache_doc.exists else {}
    initial_cache_size = len(trans_cache)

    print(f"[로손] 맞춤형 하이브리드 번역 시작... (현재 번역 노트에 {initial_cache_size}개 기억 중)")
    lawson_data = []
    seen_titles = set()

    try:
        response = requests.get(LAWSON_URL, headers=headers, timeout=10)
        # 사장님이 쓰셨던 갓벽한 utf-8 설정 그대로 유지!
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

                # 🌟 사장님이 원하신 바로 그 기능: 상세 페이지 링크 정확히 추출!
                a_tag = item.select_one("a")
                item_href = a_tag.get('href') if a_tag else ""
                item_url = urljoin("https://www.lawson.co.jp", item_href) if item_href else ""

                price_tag = item.select_one("p.price, .price")
                raw_price = price_tag.text.strip() if price_tag else ""

                date_tag = item.select_one("p.date, .date")
                raw_launch = date_tag.text.strip() if date_tag else "진행 중인 신상품"

                raw_kcal = ""
                for p_tag in item.find_all('p'):
                    if 'kcal' in p_tag.text.lower():
                        raw_kcal = p_tag.text.strip()
                        break
                
                raw_region = "전국 (일부 점포 제외)" 

                # 🧠 DeepL 번역 모듈 적용
                kr_title = smart_translate(raw_title, trans_cache, deepl_key)
                kr_price = smart_translate(raw_price, trans_cache, deepl_key) if raw_price else ""
                kr_launch = smart_translate(raw_launch, trans_cache, deepl_key) if raw_launch else ""
                
                # 칼로리는 번역기 낭비 방지를 위해 텍스트 교체로 유지
                kr_kcal = raw_kcal.replace("当たり", " 당 ").replace("食", "식").replace("個入", "개입")
                time.sleep(0.1) 

                if not is_spam(kr_title):
                    lawson_data.append({
                        "category": "🏪 편의점",
                        "brand": "로손",
                        "title": kr_title,
                        "price": kr_price,
                        "date": kr_launch,
                        "region": raw_region,
                        "itemUrl": item_url, # ⬅️ 완벽하게 긁어온 상세 링크 저장!
                        "kcal": kr_kcal, 
                        "week": "", 
                        "imageUrl": ""
                    })
                    seen_titles.add(raw_title)
                    print(f"  -> 수집됨: {kr_title} / {kr_kcal}")
                    
        # 🧠 크롤링이 끝나면 새로 추가된 번역 단어들을 파이어베이스 노트에 업데이트!
        if len(trans_cache) > initial_cache_size:
            cache_ref.set(trans_cache)
            print(f"✅ 번역 노트에 {len(trans_cache) - initial_cache_size}개의 새로운 단어가 추가로 기억되었습니다!")

    except Exception as e:
        print(f"🚨 로손 에러: {e}")
        
    return lawson_data

if __name__ == "__main__":
    firebase_key_str = os.environ.get('FIREBASE_KEY')
    deepl_key = os.environ.get('DEEPL_KEY')
    
    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        # 💡 캐시를 넘겨주기 위해 DB를 먼저 세팅
        db = firestore.client()
        
        lawson_items = crawl_lawson(db, deepl_key)
        
        if lawson_items:
            db.collection("crawled_events").document("로손").set({"items": lawson_items})
            print(f"✅ 로손 파이어베이스 업데이트 성공! (총 {len(lawson_items)}개) 🚀")
        else:
            print("🚨 FIREBASE_KEY 에러 또는 수집된 데이터 없음")
    else:
        print("🚨 FIREBASE_KEY 에러")
