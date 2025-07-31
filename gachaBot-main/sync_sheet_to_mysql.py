import pymysql
import gspread
import pandas as pd
import datetime
import json
from google.oauth2.service_account import Credentials

def get_conn():
    return pymysql.connect(
        host='34.68.132.37', user='admin', password='ahrvysmswkehdghk', db='bot',
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
    )

def safe_json(val):
    if val in [None, '', 'None']:
        return None
    try:
        # 만약 val이 이미 dict 형식이면 json.dumps 해줌
        if isinstance(val, dict):
            return json.dumps(val, ensure_ascii=False)
        # 아니면 str 타입이라 가정하고 JSON 파싱 시도 후 다시 문자열로 변환
        parsed = json.loads(val)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        # JSON 파싱 안 되면 그냥 문자열로 저장 (또는 None으로 처리 가능)
        return val

def safe_datetime(val):
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if val in ['', 'None', 'NaT']:
            return None
        try:
            return pd.to_datetime(val).to_pydatetime()
        except Exception:
            return None
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return None
        return val.to_pydatetime()
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
            attention INT,
            power INT,
            obs INT,
            luck INT,
            wilpower INT,
            san int,
            coin INT,
            gain_path TEXT,
            auth_time DATETIME,
            lottery_count INT DEFAULT 0,
            last_lottery_time date
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
            favor_score json,
            favor_status VARCHAR(64),
            complete BOOLEAN
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

def ensure_gacha_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gacha (
            item_name VARCHAR(255),
            answer_list TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

def ensure_frichcon_table_exists(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS frichcon (
            명령어 TEXT NOT NULL,
            출력 TEXT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

# 동기화 함수들
def sync_auth(conn):
    try:
        df = pd.DataFrame(get_ws('1AKF6DY4JatQCQcbatcjPqEyez-yk17X9SwFgZHrBPao', '인증').get_all_records())
        if df.empty:
            print("❗ 인증 시트에 데이터가 없습니다.")
            return
        df = df.where(pd.notnull(df), None)
        with conn.cursor() as cur:
            ensure_auth_table_exists(cur)
            cur.execute("DELETE FROM auth")
            for _, row in df.iterrows():
                cur.execute("""
                    INSERT INTO auth (
                        id_code, name, userId, job, height,
                        attention, power, obs, luck, wilpower, san,
                        coin, gain_path, auth_time, lottery_count,  last_lottery_time
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name=VALUES(name),
                        userId=VALUES(userId),
                        job=VALUES(job),
                        height=VALUES(height),
                        attention=VALUES(attention),
                        power=VALUES(power),
                        obs=VALUES(obs),
                        luck=VALUES(luck),
                        wilpower=VALUES(wilpower),
                        san=VALUES(san),
                        coin=VALUES(coin),
                        gain_path=VALUES(gain_path),
                        auth_time=VALUES(auth_time),
                        lottery_count=VALUES(lottery_count),
                        last_lottery_time=VALUES(last_lottery_time)
                """, (
                    row['id_code'],
                    row['Name'],
                    row['userId'],
                    row['직업'],
                    safe_float(row['키']),
                    safe_int(row['주목도']),
                    safe_int(row['힘']),
                    safe_int(row['관찰']),
                    safe_int(row['행운']),
                    safe_int(row['지력']),
                    safe_int(row['정신력']),
                    safe_int(row['소지금'], default=None),
                    row['획득 경로'] if row['획득 경로'] not in [None, '', 'None'] else None,
                    safe_datetime(row['인증시각']),
                    safe_int(row.get('복권 구매 수', 0)),
                    safe_datetime(row.get('복권 구매일'))
                ))
        conn.commit()
        print("✅ 인증 시트 → 'auth' 테이블 동기화 완료")
    except Exception as e:
        print(f"❌ 인증 시트 동기화 중 오류 발생: {e}")

def sync_settlement(conn):
    try:
        df = pd.DataFrame(get_ws('1AKF6DY4JatQCQcbatcjPqEyez-yk17X9SwFgZHrBPao', '정산').get_all_records())
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
                        pending_count, last_tweet_count, total_coin, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row['Name'],
                    row['소지품'],
                    row['아이템 매각 대기'],
                    safe_int(row['툿수']),
                    safe_int(row['정산 대기']),
                    safe_int(row['정산 툿수']),
                    safe_int(row['지불 코인']),
                    safe_datetime(row['마지막 정산'])
                ))
        conn.commit()
        print("✅ 정산 시트 → 'settlements' 테이블 동기화 완료")
    except Exception as e:
        print(f"❌ 정산 시트 동기화 중 오류 발생: {e}")

def sync_favor(conn):
    try:
        df = pd.DataFrame(get_ws('1AKF6DY4JatQCQcbatcjPqEyez-yk17X9SwFgZHrBPao', '호감도').get_all_records())
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
                        favor_status, complete
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    row['Name'],
                    row['호감 아이템'],
                    row['불호 아이템'],
                    safe_json(row['호감점수']),
                    row['호감도 현황'],
                    bool(row['컴플리트'])
                ))
        conn.commit()
        print("✅ 호감도 시트 → 'favor' 테이블 동기화 완료")
    except Exception as e:
        print(f"❌ 호감도 시트 동기화 중 오류 발생: {e}")

def sync_gacha(conn):
    try:
        df = pd.DataFrame(get_ws('1AKF6DY4JatQCQcbatcjPqEyez-yk17X9SwFgZHrBPao', '가챠').get_all_records())
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

def sync_frichcon(conn):
    try:
        df = pd.DataFrame(get_ws('1AKF6DY4JatQCQcbatcjPqEyez-yk17X9SwFgZHrBPao', '수염').get_all_records())
        if df.empty:
            print("❗ '수염' 시트에 데이터가 없습니다.")
            return
        df = df.replace('', None)
        with conn.cursor() as cur:
            ensure_frichcon_table_exists(cur)
            cur.execute("DELETE FROM frichcon")
            for row in df.to_dict(orient='records'):
                cur.execute(
                    "INSERT INTO frichcon (명령어, 출력) VALUES (%s, %s)",
                    (row.get('명령어'), row.get('출력'))
                )
        conn.commit()
        print("✅ '수염' 시트 → 'frichcon' 테이블 동기화 완료")
    except Exception as e:
        print(f"❌ '수염' 시트 동기화 중 오류 발생: {e}")

def run():
    conn = get_conn()
    try:
        sync_auth(conn)
        sync_settlement(conn)
        sync_favor(conn)
        sync_gacha(conn)
        sync_frichcon(conn)
        print("\u2705 Google Sheets → MySQL 동기화 완료")
    finally:
        conn.close()

if __name__ == '__main__':
    run()
