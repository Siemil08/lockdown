import pymysql
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime

# MySQL 연결
conn = pymysql.connect(
    host='34.68.132.37',
    user='admin',
    password='ahrvysmswkehdghk',
    db='bot',
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)

# Google Sheets 연결 (복수 문서 지원)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('service_account.json', scopes=scope)
gc = gspread.authorize(creds)

# 기존 시트 (auth, settlements, favor)
sheet_main = gc.open_by_key('1AKF6DY4JatQCQcbatcjPqEyez-yk17X9SwFgZHrBPao')

# 봇입금 시트 (별도 키)
sheet_bot_input = gc.open_by_key('1IjvCaTHotpBGH-bzUMpv6FQYzQvuXz-aEnJy9e-4QLg')

def format_dates(df):
    """datetime 형식을 문자열로 변환"""
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]) or isinstance(df[col].iloc[0], datetime):
            df[col] = df[col].astype(str)
    return df

def write_df_to_sheet(df, worksheet_name, sheet_obj):
    if df.empty:
        print(f"⚠️ [{worksheet_name}] 데이터프레임이 비어 있습니다. 건너뜀.")
        return
    
    try:
        worksheet = sheet_obj.worksheet(worksheet_name)
    except Exception as e:
        print(f"❌ 워크시트 '{worksheet_name}'를 찾을 수 없습니다: {e}")
        print("➡️ 현재 워크시트 목록:", [ws.title for ws in sheet_obj.worksheets()])
        return

    df = df.fillna('')
    df = format_dates(df)
    df = df.astype(str)
    data = df.values.tolist()

    # 범위 자동 계산
    num_rows, num_cols = df.shape
    if num_cols <= 26:
        end_col = chr(64 + num_cols)  # A=65
    else:
        # 26 초과 컬럼인 경우 임시로 Z로 제한
        end_col = 'Z'
    clear_range = f"A2:{end_col}{num_rows + 1}"

    try:
        print(f"📝 [{worksheet_name}] 시트 초기화 중: {clear_range}")
        worksheet.batch_clear([clear_range])
        print(f"📤 [{worksheet_name}] 데이터 업데이트 중... ({num_rows}행)")
        worksheet.update(range_name="A2", values=data)
        print(f"✅ [{worksheet_name}] 업데이트 완료!")
    except Exception as e:
        print(f"❌ [{worksheet_name}] 업데이트 실패: {e}")

def export_table(table_name, worksheet_name):
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table_name}")
            rows = cur.fetchall()
            df = pd.DataFrame(rows)
            print(f"🔎 [{table_name}] {len(df)}행 가져옴.")
            write_df_to_sheet(df, worksheet_name, sheet_main)
    except Exception as e:
        print(f"❌ [{table_name}] 데이터베이스 쿼리 실패: {e}")

def export_bot_input():
    try:
        with conn.cursor() as cur:
            # id 제외하고 timestamp, bot_response만 선택
            cur.execute("SELECT timestamp, bot_response FROM bot_input ORDER BY timestamp DESC")
            rows = cur.fetchall()
            df = pd.DataFrame(rows)
            print(f"🔎 [bot_input] {len(df)}행 가져옴.")
            write_df_to_sheet(df, '봇입금', sheet_bot_input)
    except Exception as e:
        print(f"❌ [bot_input] 데이터베이스 쿼리 실패: {e}")

def run():
    export_table('auth', '인증')
    export_table('settlements', '정산')
    export_table('favor', '호감도')
    export_bot_input()
    print("🎉 전체 MySQL → Google Sheets 복사 완료")

if __name__ == '__main__':
    run()
