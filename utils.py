import pymysql
from flask import jsonify
from datetime import datetime, timedelta
import pytz
import random
import re

KST = pytz.timezone('Asia/Seoul')

# db연결
def get_conn():
    return pymysql.connect(
        host='34.68.132.37', user='admin', password='ahrvysmswkehdghk', db='bot',
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
    )

# 대답 생성
def create_response(msg):
    return jsonify({
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": msg}}]}
    })

#로그저장 함수
def insert_log_entry(user_id, id_code, name, user_input, log_type, select_path, bot_response, table_name='Total_log'):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO `{table_name}` (
                    timestamp, user_id, id_code, name,
                    user_input, type, select_path, bot_response
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(), user_id, id_code, name,
                user_input, log_type, select_path, bot_response
            ))
        conn.commit()
    except Exception as e:
        print(f"[ERROR] 로그 삽입 중 오류: {e}")
    finally:
        conn.close()

# 오후 9시에서 10시 사이에만 구동
def is_operating_hour():
    now = datetime.now(KST)
    return 21 <= now.hour <= 22

# 조사타입 자동 파
def get_survey_type_by_day():
    now = datetime.now(KST)
    weekday = now.weekday()
    if weekday in range(0, 4):
        return '일상조사'
    elif weekday in [4, 5]:
        return '비일상조사'
    else:
        return '일상조사'

# [] 안의 내용만 추출
def extract_bracket_content(text):
    match = re.search(r'\[(.*?)\]', text)
    return match.group(1).strip() if match else ''

# 18시간 만에 접속시 
def is_long_time_no_see(last_time, hours=18):
    try:
        last_dt = datetime.strptime(last_time, '%Y-%m-%d %H:%M:%S')
        return (datetime.now() - last_dt) > timedelta(hours=hours)
    except Exception:
        return False

# 랜덤 키워드 추출
def get_random_answer(keyword):
    try:
        conn = get_conn()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            sql = """
                SELECT `답변 리스트` FROM `random`
                WHERE `랜덤 키워드` = %s LIMIT 1
            """
            cur.execute(sql, (keyword.strip(),))
            row = cur.fetchone()
            if row and row.get('답변 리스트'):
                options = row['답변 리스트'].split(',')
                options = [opt.strip() for opt in options if opt.strip()]
                if options:
                    return random.choice(options)
    except Exception as e:
        print(f"[ERROR] get_random_answer 오류: {e}")
    finally:
        conn.close()

    return '랜덤 정보가 없습니다'

def fill_random_in_text(text):
    def replacer(match):
        keyword = match.group(1) or match.group(2)
        return get_random_answer(keyword)
    return re.sub(r'\{랜덤(?::\s*([^\}]+))?\}', replacer, text)

