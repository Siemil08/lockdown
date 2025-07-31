import re
from collections import Counter

# 시트에서 열 이름으로 열 인덱스 찾기
def get_column_index(ws, column_name):
    headers = ws.row_values(1)
    return headers.index(column_name) + 1

# HTML 태그 제거
def clean_html_tags(text):
    return re.sub(r'<[^>]+>', '', text).strip()

# 아이템 문자열 파싱 (쉼표, 공백 구분)
def parse_items(text):
    return [i.strip() for i in re.split(r'[,\s]+', text) if i.strip()]

# 소지품 카운팅
def count_items(items):
    return Counter(items)
