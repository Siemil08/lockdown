import re
import random
from datetime import datetime, timedelta, date
import pytz

# 정수변환
def safe_int(value, default=0):
    try:
        return int(value)
    except:
        return default

# 한국 시간
def get_kst_now():
    return datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(pytz.timezone("Asia/Seoul"))

# 일요일 오후 10시 확인
def get_next_sunday_10pm(after_time):
    days_ahead = 6 - after_time.weekday()  # 일요일까지 남은 일수 계산
    if days_ahead < 0:
        days_ahead += 7
    next_sunday = (after_time + timedelta(days=days_ahead)).replace(hour=22, minute=0, second=0, microsecond=0)
    return next_sunday

# 복권 리셋
def is_lottery_reset_required(last_updated):
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)

    # 가장 최근의 일요일 오후 10시 계산
    last_reset = now - timedelta(days=(now.weekday() + 1) % 7)
    last_reset = last_reset.replace(hour=22, minute=0, second=0, microsecond=0)

    # last_updated가 date 객체면서 datetime 객체가 아니면 datetime으로 변환
    if isinstance(last_updated, date) and not isinstance(last_updated, datetime):
        last_updated = datetime.combine(last_updated, datetime.min.time())

    # last_updated가 naive라면 KST 시간대로 변환
    if last_updated.tzinfo is None or last_updated.tzinfo.utcoffset(last_updated) is None:
        last_updated = KST.localize(last_updated)

    return last_updated < last_reset

def handle_frichcon(conn, username, content):
    """
    content에 [명령어] 형식이 있을 경우, 해당 명령어가 frichcon 테이블에 존재하면
    출력 컬럼의 값을 무작위로 반환. 없으면 None.
    만약 출력 내용에 '코인' + 숫자가 있으면 숫자만큼 auth.coin 증가시키고
    bot_input 테이블에 입금 로그 기록
    """
    try:
        print(f"[DEBUG] handle_frichcon() 진입 - 사용자: {username}, 원본 입력: {content}")

        # 대괄호 안의 텍스트 추출
        match = re.search(r'\[(.*?)\]', content)
        if not match:
            print(f"[DEBUG] 대괄호 명령어 없음. 패스.")
            return None

        keyword = match.group(1).strip()
        print(f"[DEBUG] 추출된 명령어 키워드: '{keyword}'")

        # 복권 구매 로직
        if keyword.startswith("복권 구매"):
            count_match = re.search(r'복권 구매\s*(\d*)', keyword)
            buy_count = safe_int(count_match.group(1), 1)
            if buy_count < 1:
                buy_count = 1
            if buy_count > 3:
                return "복권은 최대 3장까지만 구매할 수 있습니다."

            with conn.cursor() as cur:
                # auth 테이블에서 사용자 정보 확인
                cur.execute("SELECT coin, last_lottery_time, lottery_count FROM auth WHERE name = %s", (username,))
                row = cur.fetchone()
                if not row:
                    return "인증된 사용자만 복권을 구매할 수 있습니다."

                coin = safe_int(row['coin'])
                lottery_count = safe_int(row['lottery_count'])
                last_lottery_time = row['last_lottery_time'] or datetime(2000,1,1)
                
                # 리셋 여부 판단
                if is_lottery_reset_required(last_lottery_time):
                    print(f"[DEBUG] 복권 구매 기록 리셋")
                    lottery_count = 0

                if lottery_count + buy_count > 3:
                    return "금주에 구매할 수 있는 복권을 모두 구입하셨습니다."

                total_cost = buy_count * 3
                if coin < total_cost:
                    return f"코인이 부족합니다. (필요: {total_cost}코인, 보유: {coin}코인)"

                # 코인 차감 및 구매 수 증가
                new_coin = coin - total_cost
                new_count = lottery_count + buy_count
                now = datetime.now(pytz.timezone('Asia/Seoul'))

                cur.execute("""
                    UPDATE auth 
                    SET coin = %s, lottery_count = %s, last_lottery_time = %s
                    WHERE name = %s
                """, (new_coin, new_count, now, username))

                log_message = f"{username}님이 복권 {buy_count}장 구매하여 {total_cost}코인을 사용했습니다. (남은 코인: {new_coin})"
                cur.execute("INSERT INTO bot_input (timestamp, bot_response) VALUES (%s, %s)", (now.strftime('%Y-%m-%d %H:%M:%S'), log_message))
                conn.commit()

                return log_message

        # 일반 키워드 로직
        with conn.cursor() as cur:
            cur.execute("SELECT 출력 FROM frichcon WHERE 명령어 = %s", (keyword,))
            rows = cur.fetchall()

            print(f"[DEBUG] '{keyword}'에 해당하는 명령어 {len(rows)}개 발견")

            if not rows:
                return None

            # 무작위 행 선택
            selected_row = random.choice(rows)
            output_text = selected_row['출력']
            print(f"[DEBUG] 선택된 출력 원본: {output_text}")

            # 쉼표 분리 시 랜덤 출력
            options = [opt.strip() for opt in output_text.split(';') if opt.strip()]
            selected_final = random.choice(options) if len(options) > 1 else output_text.strip()

            print(f"[DEBUG] 최종 출력: {selected_final}")

            # '코인' + 숫자 패턴 찾기 (예: 코인5, 코인 10 등)
            coin_matches = re.findall(r'코인\s*(\d+)', selected_final)
            if coin_matches:
                total_coin = sum(int(num) for num in coin_matches)
                print(f"[DEBUG] 코인 증가 감지: +{total_coin} 코인")

                # 사용자 현재 코인 조회 및 업데이트
                cur.execute("SELECT coin FROM auth WHERE name = %s", (username,))
                row = cur.fetchone()
                if not row:
                    print(f"[WARN] {username} 님 인증 사용자 아님 - 코인 증가 생략")
                else:
                    current_coin = safe_int(row['coin'])
                    new_coin = current_coin + total_coin
                    cur.execute("UPDATE auth SET coin = %s WHERE name = %s", (new_coin, username))

                    # bot_input 테이블에 로그 기록
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    log_message = f"{username}님이 {total_coin}코인을 획득했습니다. (누적: {new_coin}코인)"
                    cur.execute("INSERT INTO bot_input (timestamp, bot_response) VALUES (%s, %s)", (timestamp, log_message))
                    print(f"[DEBUG] 코인 획득 로그 기록 완료")

                conn.commit()

            return selected_final

    except Exception as e:
        print(f"[ERROR] [{username}] frichcon 처리 중 예외 발생: {e}")
        return None
