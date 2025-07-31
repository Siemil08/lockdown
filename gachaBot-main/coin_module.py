import re
from datetime import datetime
import pymysql

def safe_int(value, default=0):
    """안전하게 int 변환, 실패 시 default 반환"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# 그냥 정산 하면 소지금을 불러오는 코드
def load_coin(conn, username):
    with conn.cursor() as cursor:
        cursor.execute("SELECT coin FROM auth WHERE name = %s", (username,))
        result = cursor.fetchone()
        if result:
            # 딕셔너리 형태이므로 result['coin']으로 접근
            return f"{username}님의 현재 소지금은 {result['coin']}코인입니다."
        else:
            return f"{username}님은 인증된 사용자가 아닙니다."


# 정산하면 툿수 계산해서 코인도 주는 코드
def handle_balance(conn, mastodon, username):
    """
    마스토돈 계정 상태 수 기준 코인 정산 처리
    - mastodon API로 현재 상태 수 조회
    - 정산 시트에서 기존 정보 읽기
    - 신규 사용자면 시트에 추가
    - 신규 툿수 계산 후 코인 적립
    - 정산 시트 및 인증 시트 업데이트
    - 정산 결과 메시지 반환
    """
    accounts = mastodon.account_search(username, limit=1)
    if not accounts:
        return f"{username}님의 마스토돈 계정을 찾을 수 없습니다."
    user_info = accounts[0]
    current_tuts = safe_int(user_info.get('statuses_count', 0))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with conn.cursor() as cursor:
        # 정산 정보 가져오기
        cursor.execute("SELECT * FROM settlements WHERE Name = %s", (username,))
        row = cursor.fetchone()    

        if row:
            last_tuts = safe_int(row['last_tweet_count'])  # 툿수
            pending_tuts = safe_int(row['pending_count'])  # 정산 대기
            total_coin = safe_int(row['total_coin']) # 지불 코인
            row_exists = True
        else:
            last_tuts = pending_tuts = total_coin = 0
            row_exists = False

        new_tuts = (current_tuts - last_tuts) + pending_tuts
        reward_coin = (new_tuts // 100) * 2
        leftover_tuts = new_tuts % 100
        new_total_coin = total_coin + reward_coin

        if row_exists:
            cursor.execute("""
                UPDATE settlements
                SET tweet_count = %s, last_tweet_count = %s, pending_count = %s, total_coin = %s, updated_at = %s
                WHERE name = %s
            """, (current_tuts, current_tuts, leftover_tuts, new_total_coin, now, username))
            conn.commit()
        else:
            cursor.execute("""
                INSERT INTO settlements (name, tweet_count, last_tweet_count, pending_count, total_coin, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, current_tuts, current_tuts, leftover_tuts, new_total_coin, now))
            conn.commit()

        # 인증 테이블 코인 업데이트 및 현재 소지금 조회
        cursor.execute("SELECT coin FROM auth WHERE name = %s", (username,))
        auth_row = cursor.fetchone()
        if auth_row:
            current_coin = safe_int(auth_row['coin'])
            updated_coin = current_coin + reward_coin
            cursor.execute("UPDATE auth SET coin = %s WHERE name = %s", (updated_coin, username))
        else:
            return f"{username}님은 인증된 사용자가 아닙니다."

    conn.commit()
    return (
        f"이번 정산으로 {reward_coin}코인을 획득했습니다.\n"
        f"현재 소지 코인: {updated_coin}코인\n"
    )

def handle_coin_transfer(conn, giver, content):
    """
    코인 양도 처리
    - 입력 형식: [코인 양도] [받는 사람] [금액]
    - 양도자/수령자 인증 확인
    - 보유 코인 충분 시 양도 실행, 시트 업데이트
    - 결과 메시지 반환
    """
    match = re.search(r'\[코인\s*양도\]\s*\[([^\[\]]+)\]\s*\[(\d+)\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다.\n예: [코인 양도] [받는 사람] [10]"

    receiver = match.group(1).strip()
    amount = int(match.group(2))

    with conn.cursor() as cursor:
        cursor.execute("SELECT Name, coin FROM auth WHERE name IN (%s, %s)", (giver, receiver))
        users = cursor.fetchall()

        user_data = {row['Name']: safe_int(row['coin']) for row in users}
        if giver not in user_data or receiver not in user_data:
            return "인증되지 않은 사용자입니다."

        if user_data[giver] < amount:
            return f"{giver}님의 소지금이 부족하여 코인 양도가 불가능합니다. (보유: {user_data[giver]})"

        # 코인 이동
        cursor.execute("UPDATE auth SET coin = coin - %s WHERE Name = %s", (amount, giver))
        cursor.execute("UPDATE auth SET coin = coin + %s WHERE Name = %s", (amount, receiver))

    conn.commit()
    return f"{giver}님이 {receiver}님에게 {amount}코인을 양도하였습니다."


def handle_coin_gain(conn, username, content):
    """
    자율 코인 입력 처리
    - 입력 형식: [코인 획득] [금액]
    - 인증 사용자 확인 후 소지금 증가
    - bot_input 테이블에 획득 내역 기록
    """
    match = re.search(r'\[코인\s*획득\]\s*\[(\d+)\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다.\n예: [코인 획득] [5]"

    amount = int(match.group(1))

    with conn.cursor() as cursor:
        # 인증 사용자 정보 조회 및 코인 현재값 확인
        cursor.execute("SELECT coin FROM auth WHERE name = %s", (username,))
        row = cursor.fetchone()
        if not row:
            return f"{username}님은 인증된 사용자가 아닙니다."
        
        current_coin = safe_int(row['coin'])
        new_coin = current_coin + amount

        # 코인 업데이트
        cursor.execute("UPDATE auth SET coin = %s WHERE name = %s", (new_coin, username))

        # 로그 기록
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"{username}님이 {amount}코인을 획득했습니다. (누적: {new_coin}코인)"
        cursor.execute("INSERT INTO bot_input (timestamp, bot_response) VALUES (%s, %s)", (timestamp, log_message))

    conn.commit()
    return f"{username}님이 {amount}코인을 획득하였습니다."
