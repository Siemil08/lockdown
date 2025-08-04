import pymysql
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

def get_conn():
    return pymysql.connect(
        host='34.68.132.37', 
        user='admin', 
        password='ahrvysmswkehdghk', 
        db='bot',
        charset='utf8mb4', 
        cursorclass=pymysql.cursors.DictCursor
    )

def get_ws(sheet_key, sheet_name):
    creds = Credentials.from_service_account_file('service_account.json', scopes=[
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ])
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(sheet_key)
    return sheet.worksheet(sheet_name)

def ensure_josa_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS 조사 (
            선택경로 TEXT,
            장소1 TEXT,
            장소2 TEXT,
            장소3 TEXT,
            장소4 TEXT,
            장소5 TEXT,
            타겟 TEXT,
            조건 TEXT,
            조건2 TEXT,
            조건3 TEXT,
            출력지문 TEXT,
            선택지 TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

def sync_josa(conn):
    df = pd.DataFrame(get_ws(
        '1AKF6DY4JatQCQcbatcjPqEyez-yk17X9SwFgZHrBPao', 
        '조사'
    ).get_all_records())

    df = df.where(pd.notnull(df), None).replace('', None)

    with conn.cursor() as cur:
        ensure_josa_table_exists(cur)
        cur.execute("DELETE FROM 조사")
        for row in df.to_dict(orient='records'):
            cur.execute("""
                INSERT INTO 조사 (선택경로, 장소1, 장소2, 장소3, 장소4, 장소5, 타겟,
                조건, 조건2, 조건3, 출력지문, 선택지)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row.get('선택경로'), row.get('장소1'), row.get('장소2'), row.get('장소3'), row.get('장소4'),
                row.get('장소5'), row.get('타겟'), row.get('조건'), row.get('조건2'),
                row.get('조건3'), row.get('출력지문'), row.get('선택지')
            ))
    conn.commit()
    print("✅ 조사(josa) 테이블 초기화 후 동기화 완료")

def run():
    conn = get_conn()
    try:
        sync_josa(conn)
    finally:
        conn.close()

if __name__ == '__main__':
    run()
