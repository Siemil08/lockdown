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
            return f"{username}님의 현재 소지금은 {result['coin']}코인입니다."
        else:
            return f"{username}님은 인증된 사용자가 아닙니다."

# 정산하면 툿수 계산해서 코인도 주는 코드
def handle_balance(conn, mastodon, mastodon_id):
    """
    마스토돈 아이디 기준 정산 처리
    - mastodon_id로 mastodon API에서 상태 수 조회
    - auth 테이블에서 이름(name) 조회
    - settlements 테이블에서 정산 데이터 조회 및 업데이트 (mastodon_id 기준)
    - 인증 테이블 coin 업데이트 (mastodon_id 기준)
    - 이름 기준 메시지 반환
    """
    accounts = mastodon.account_search(mastodon_id, limit=1)
    if not accounts:
        return f"마스토돈 계정을 찾을 수 없습니다: {mastodon_id}"
    user_info = accounts[0]
    current_tuts = safe_int(user_info.get('statuses_count', 0))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with conn.cursor() as cursor:
        cursor.execute("SELECT name FROM auth WHERE mastodon_id = %s", (mastodon_id,))
        auth_row = cursor.fetchone()
        if not auth_row:
            return f"{mastodon_id}님은 인증된 사용자가 아닙니다."
        username = auth_row['name']

        cursor.execute("SELECT * FROM settlements WHERE mastodon_id = %s", (mastodon_id,))
        row = cursor.fetchone()

        if row:
            last_tuts = safe_int(row['last_tweet_count'])
            pending_tuts = safe_int(row['pending_count'])
            total_coin = safe_int(row['total_coin'])
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
                WHERE mastodon_id = %s
            """, (current_tuts, current_tuts, leftover_tuts, new_total_coin, now, mastodon_id))
        else:
            cursor.execute("""
                INSERT INTO settlements (mastodon_id, tweet_count, last_tweet_count, pending_count, total_coin, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (mastodon_id, current_tuts, current_tuts, leftover_tuts, new_total_coin, now))

        cursor.execute("SELECT coin FROM auth WHERE mastodon_id = %s", (mastodon_id,))
        auth_coin_row = cursor.fetchone()
        if auth_coin_row:
            current_coin = safe_int(auth_coin_row['coin'])
            updated_coin = current_coin + reward_coin
            cursor.execute("UPDATE auth SET coin = %s WHERE mastodon_id = %s", (updated_coin, mastodon_id))
        else:
            return f"{username}님은 인증된 사용자가 아닙니다."

    conn.commit()

    return (
        f"{username}님, 이번 정산으로 {reward_coin}코인을 획득했습니다.\n"
        f"현재 소지 코인: {updated_coin}코인\n"
    )

def handle_coin_transfer(conn, giver_id, content):
    """
    코인 양도 처리 (giver_id는 마스토돈 아이디, 받는 사람은 이름)
    - 입력 형식: [코인 양도] [받는 사람(이름)] [금액]
    - 받는 사람 이름으로 auth에서 mastodon_id 조회 후 코인 양도 처리
    - 메시지는 이름 기준으로 출력
    """
    match = re.search(r'\[코인\s*양도\]\s*\[([^\[\]]+)\]\s*\[(\d+)\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다.\n예: [코인 양도] [받는 사람 이름] [10]"

    receiver_name = match.group(1).strip()
    amount = int(match.group(2))

    with conn.cursor() as cursor:
        # 양도자 정보 조회
        cursor.execute("SELECT mastodon_id, name, coin FROM auth WHERE mastodon_id = %s", (giver_id,))
        giver = cursor.fetchone()
        if not giver:
            return "양도자 인증이 되어 있지 않습니다."

        # 받는 사람 mastodon_id 조회 (이름으로 정확 일치 검색)
        cursor.execute("SELECT mastodon_id, name, coin FROM auth WHERE name = %s", (receiver_name,))
        receiver = cursor.fetchone()
        if not receiver:
            return f"받는 사람 '{receiver_name}' 님을 찾을 수 없습니다."

        # 소지금 부족 확인
        if giver['coin'] < amount:
            return f"{giver['name']}님의 소지금이 부족하여 코인 양도가 불가능합니다. (보유: {giver['coin']})"

        # 코인 차감 및 추가
        cursor.execute("UPDATE auth SET coin = coin - %s WHERE mastodon_id = %s", (amount, giver_id))
        cursor.execute("UPDATE auth SET coin = coin + %s WHERE mastodon_id = %s", (amount, receiver['mastodon_id']))

    conn.commit()

    return f"{giver['name']}님이 {receiver['name']}님에게 {amount}코인을 양도하였습니다."

def handle_coin_gain(conn, mastodon_id, content):
    """
    자율 코인 입력 처리 (마스토돈 아이디 기준)
    - 입력 형식: [코인 획득] [금액]
    - mastodon_id 기준 인증 확인 및 코인 업데이트
    - 메시지는 이름(name)으로 출력
    - bot_input 테이블에 로그 기록
    """
    match = re.search(r'\[코인\s*획득\]\s*\[(\d+)\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다.\n예: [코인 획득] [5]"

    amount = int(match.group(1))

    with conn.cursor() as cursor:
        cursor.execute("SELECT name, coin FROM auth WHERE mastodon_id = %s", (mastodon_id,))
        row = cursor.fetchone()
        if not row:
            return "인증된 사용자가 아닙니다."

        name = row['name']
        current_coin = safe_int(row['coin'])
        new_coin = current_coin + amount

        cursor.execute("UPDATE auth SET coin = %s WHERE mastodon_id = %s", (new_coin, mastodon_id))

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"{name}님이 {amount}코인을 획득했습니다. (누적: {new_coin}코인)"
        cursor.execute("INSERT INTO bot_input (timestamp, bot_response) VALUES (%s, %s)", (timestamp, log_message))

    conn.commit()
    return f"{name}님이 {amount}코인을 획득하였습니다."
