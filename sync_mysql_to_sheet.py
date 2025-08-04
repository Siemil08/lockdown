import pymysql
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

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

# Google Sheets 인증 및 문서 열기
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('service_account.json', scopes=scope)
gc = gspread.authorize(creds)

sheet_main = gc.open_by_key(MAIN_SHEET_KEY)
sheet_log = gc.open_by_key(LOG_SHEET_KEY)

# === 유틸 함수 ===
def format_dates(df):
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]) or isinstance(df[col].iloc[0], datetime):
            df[col] = df[col].astype(str)
    return df

def write_df_to_sheet(df, worksheet_name, sheet_obj):
    if df.empty:
        print(f"⚠️ [{worksheet_name}] 비어 있음. 건너뜀.")
        return

    try:
        worksheet = sheet_obj.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet_obj.add_worksheet(title=worksheet_name, rows="1000", cols="30")
        print(f"📄 워크시트 '{worksheet_name}' 새로 생성됨.")

    df = df.fillna('')
    df = format_dates(df).astype(str)
    data = df.values.tolist()

    # 범위 자동 계산
    num_rows, num_cols = df.shape
    end_col = chr(64 + num_cols) if num_cols <= 26 else 'Z'
    clear_range = f"A2:{end_col}{num_rows + 1}"

    try:
        worksheet.batch_clear([clear_range])
        worksheet.update("A2", data)
        print(f"✅ [{worksheet_name}] {num_rows}행 업데이트 완료")
    except Exception as e:
        print(f"❌ [{worksheet_name}] 업데이트 실패: {e}")

# === 테이블 내보내기 ===
def export_table(table_name, worksheet_name, sheet_obj):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table_name}")
            rows = cur.fetchall()
            df = pd.DataFrame(rows)
            print(f"🔍 [{table_name}] {len(df)}행 불러옴")
            write_df_to_sheet(df, worksheet_name, sheet_obj)

def export_bot_input():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timestamp, bot_response FROM bot_input ORDER BY timestamp DESC")
            df = pd.DataFrame(cur.fetchall())
            write_df_to_sheet(df, '봇입금', sheet_main)

def export_total_log_view():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM Total_log ORDER BY timestamp DESC LIMIT 2000")
            df = pd.DataFrame(cur.fetchall())
            write_df_to_sheet(df, 'Total_logView', sheet_log)

def export_user_logs():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT name FROM Total_log WHERE name IS NOT NULL AND name != ''")
            names = [row['name'] for row in cur.fetchall()]

        for name in names:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM Total_log 
                    WHERE name = %s 
                    ORDER BY timestamp DESC 
                    LIMIT 300
                """, (name,))
                df = pd.DataFrame(cur.fetchall())
            if not df.empty:
                sheet_name = f"{name}_log"[:100]
                write_df_to_sheet(df, sheet_name, sheet_log)

# === 실행 ===
def run_all_exports():
    export_table('auth', '인증', sheet_main)
    export_table('settlements', '정산', sheet_main)
    export_table('favor', '호감도', sheet_main)
    export_bot_input()
    export_total_log_view()
    export_user_logs()
    print("🎉 전체 MySQL → Google Sheets 내보내기 완료")

# === 진입점 ===
if __name__ == '__main__':
    run_all_exports()
