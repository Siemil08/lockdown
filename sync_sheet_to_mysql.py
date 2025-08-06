import pymysql
import gspread
import pandas as pd
import datetime
import json
from google.oauth2.service_account import Credentials

# 구글 시트 키
MAIN_SHEET_KEY = '1BiIDoNFD14mVIs2UwRUjsYwcp18DIEluSYGs2foD37s'
LOG_SHEET_KEY = '1KnCGISum5xWLzmsfewSJyKDPoyC3BCXX9-EVCW4iuE0'

# DB 연결
def get_conn():
    return pymysql.connect(
        host='35.209.172.242',
        user='admin',
        password='password1212',
        db='bot',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 안전한 데이터 변환 함수
def safe_json(val):
    if val in [None, '', 'None']:
        return None
    try:
        if isinstance(val, dict):
            return json.dumps(val, ensure_ascii=False)
        parsed = json.loads(val)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        return val

def safe_datetime(val):
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if val in ['', 'None', 'NaT']:
            return None
        try:
            return pd.to_datetime(val)
        except Exception:
            return None
    if isinstance(val, pd.Timestamp):
        return None if pd.isna(val) else val.to_pydatetime()
    if isinstance(val, datetime.datetime):
        return val
    return None

def safe_int(val, default=0):
    if val in [None, '', 'None']:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def safe_float(val, default=None):
    if val in [None, '', 'None']:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

# 구글 시트 워크시트 접근
def get_ws(sheet_key, sheet_name):
    creds = Credentials.from_service_account_file('service_account.json', scopes=[
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ])
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(sheet_key)
    return sheet.worksheet(sheet_name)

# 테이블 생성 함수들
def ensure_total_log_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Total_log (
            timestamp DATETIME,
            user_id VARCHAR(100),
            id_code VARCHAR(64),
            name VARCHAR(64),
            input TEXT,
            type VARCHAR(64),
            select_path TEXT,
            bot_response TEXT,
            PRIMARY KEY (timestamp, name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

def ensure_auth_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth (
            id_code VARCHAR(64) PRIMARY KEY,
            name VARCHAR(64),
            userId VARCHAR(100),
            job VARCHAR(64),
            height FLOAT,
            power INT,
            obs INT,
            luck INT,
            wilpower INT,
            san INT,
            coin INT,
            gain_path TEXT,
            auth_time DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

def ensure_settlements_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settlements (
            name VARCHAR(64) PRIMARY KEY,
            inventory TEXT,
            sell_pending TEXT,
            tweet_count INT,
            pending_count INT,
            last_tweet_count INT,
            total_coin INT,
            updated_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

def ensure_favor_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favor (
            name VARCHAR(64) PRIMARY KEY,
            favor_items TEXT,
            dislike_items TEXT,
            favor_score JSON,
            favor_status VARCHAR(64),
            complete text
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

def ensure_gacha_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gacha (
            item_name VARCHAR(255),
            answer_list TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

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

def ensure_random_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS random (
            `답변 리스트` TEXT,
            `랜덤 키워드` VARCHAR(255)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

# 동기화 함수들
def sync_auth(conn):
    df = pd.DataFrame(get_ws(MAIN_SHEET_KEY, '인증').get_all_records())
    if df.empty:
        print("❗ 인증 시트에 데이터가 없습니다.")
        return
    df = df.where(pd.notnull(df), None).replace('', None)
    with conn.cursor() as cur:
        ensure_auth_table_exists(cur)
        cur.execute("DELETE FROM auth")
        for _, row in df.iterrows():
            cur.execute("""
            INSERT INTO auth (
                id_code, name, userId, job, height,
                power, obs, luck, wilpower, san,
                coin, gain_path, auth_time, mastodon_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            row.get('id_code'),
            row.get('Name'),
            row.get('userId'),
            row.get('직업'),
            safe_float(row.get('키')),
            safe_int(row.get('힘')),
            safe_int(row.get('관찰')),
            safe_int(row.get('행운')),
            safe_int(row.get('지능')),
            safe_int(row.get('정신력')),
            safe_int(row.get('소지금')),
            row.get('획득 경로'),
            safe_datetime(row.get('인증시각')),
            row.get('mastodon_id')
        ))
    conn.commit()
    print("✅ 인증(auth) 테이블 초기화 후 동기화 완료")

def sync_josa(conn):
    df = pd.DataFrame(get_ws(MAIN_SHEET_KEY, '조사').get_all_records())
    df = df.where(pd.notnull(df), None).replace('', None)
    with conn.cursor() as cur:
        ensure_josa_table_exists(cur)
        cur.execute("DELETE FROM 조사")
        for row in df.to_dict(orient='records'):
            cur.execute("""
                INSERT INTO 조사 (
                    선택경로, 장소1, 장소2, 장소3, 장소4, 장소5,
                    타겟, 조건, 조건2, 조건3, 출력지문, 선택지
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row.get('선택경로'), row.get('장소1'), row.get('장소2'), row.get('장소3'),
                row.get('장소4'), row.get('장소5'), row.get('타겟'), row.get('조건'),
                row.get('조건2'), row.get('조건3'), row.get('출력지문'), row.get('선택지')
            ))
    conn.commit()
    print("✅ 조사(josa) 테이블 초기화 후 동기화 완료")

def sync_random(conn):
    df = pd.DataFrame(get_ws(MAIN_SHEET_KEY, '랜덤').get_all_records())
    df = df.where(pd.notnull(df), None).replace('', None)
    with conn.cursor() as cur:
        ensure_random_table_exists(cur)
        cur.execute("DELETE FROM random")
        for row in df.to_dict(orient='records'):
            cur.execute("""
                INSERT INTO random (`랜덤 키워드`, `답변 리스트`)
                VALUES (%s, %s)
            """, (
                row.get('랜덤 키워드'), row.get('답변 리스트')
            ))
    conn.commit()
    print("✅ 랜덤 시트 → 'random' 테이블 동기화 완료")

def sync_settlement(conn):
    try:
        df = pd.DataFrame(get_ws(MAIN_SHEET_KEY, '정산').get_all_records())
        if df.empty:
            print("❗ 정산 시트에 데이터가 없습니다.")
            return
        df = df.replace('', None)
        with conn.cursor() as cur:
            ensure_settlements_table_exists(cur)
            for row in df.to_dict(orient='records'):
                cur.execute("""
                    REPLACE INTO settlements (
                        name, inventory, sell_pending, tweet_count,
                        pending_count, last_tweet_count, total_coin, updated_at, mastodon_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row['Name'],
                    row['소지품'],
                    row['아이템 매각 대기'],
                    safe_int(row['툿수']),
                    safe_int(row['정산 대기']),
                    safe_int(row['정산 툿수']),
                    safe_int(row['지불 코인']),
                    safe_datetime(row['마지막 정산']),
                    row.get('mastodon_id')
                ))
        conn.commit()
        print("✅ 정산 시트 → 'settlements' 테이블 동기화 완료")
    except Exception as e:
        print(f"❌ 정산 시트 동기화 중 오류 발생: {e}")

def sync_favor(conn):
    try:
        df = pd.DataFrame(get_ws(MAIN_SHEET_KEY, '호감도').get_all_records())
        if df.empty:
            print("❗ 호감도 시트에 데이터가 없습니다.")
            return
        df = df.replace('', None)
        with conn.cursor() as cur:
            ensure_favor_table_exists(cur)
            for row in df.to_dict(orient='records'):
                cur.execute("""
                    REPLACE INTO favor (
                        name, favor_items, dislike_items, favor_score,
                        favor_status, complete, mastodon_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    row['Name'],
                    row['호감 아이템'],
                    row['불호 아이템'],
                    safe_json(row['호감점수']),
                    row['호감도 현황'],
                    row['컴플리트'],
                    row.get('mastodon_id')
                ))
        conn.commit()
        print("✅ 호감도 시트 → 'favor' 테이블 동기화 완료")
    except Exception as e:
        print(f"❌ 호감도 시트 동기화 중 오류 발생: {e}")

def sync_gacha(conn):
    try:
        df = pd.DataFrame(get_ws(MAIN_SHEET_KEY, '가챠').get_all_records())
        if df.empty:
            print("❗ 가챠 시트에 데이터가 없습니다.")
            return
        df = df.replace('', None)
        with conn.cursor() as cur:
            ensure_gacha_table_exists(cur)
            cur.execute("DELETE FROM gacha")
            for row in df.to_dict(orient='records'):
                cur.execute(
                    "INSERT INTO gacha (item_name, answer_list) VALUES (%s, %s)",
                    (row.get('아이템명'), row.get('답변 리스트'))
                )
        conn.commit()
        print("✅ 가챠 시트 → 'gacha' 테이블 동기화 완료")
    except Exception as e:
        print(f"❌ 가챠 시트 동기화 중 오류 발생: {e}")

def run():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            ensure_total_log_table_exists(cur)
            ensure_auth_table_exists(cur)
            ensure_settlements_table_exists(cur)
            ensure_favor_table_exists(cur)
            ensure_gacha_table_exists(cur)
            ensure_josa_table_exists(cur)
            ensure_random_table_exists(cur)
        sync_auth(conn)
        sync_settlement(conn)
        sync_favor(conn)
        sync_gacha(conn)
        sync_josa(conn)
        sync_random(conn)
        print("\u2705 Google Sheets → MySQL 동기화 완료")
    finally:
        conn.close()

if __name__ == '__main__':
    run()
