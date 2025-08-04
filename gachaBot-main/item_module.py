import re
import json
import random
from collections import Counter
import pymysql

def parse_item_name(item_name_str):
    if not item_name_str:  # None 혹은 빈 문자열일 때
        return []
    # 예시: '아이템A, 아이템B, 아이템A' 같은 문자열을 리스트로 변환
    return [item.strip() for item in item_name_str.split(',') if item.strip()]

# 소숫점 쓰면?
def safe_float(value, default=0.0):
    try:
        str_value = str(value)
        # 숫자와 소수점을 포함하는 부분만 추출 (예: "123.45코인" -> "123.45")
        match = re.search(r'\d+(\.\d+)?', str_value)
        if match:
            return float(match.group())
        else:
            return default
    except (ValueError, TypeError):
        return default

# 그냥 정수 계산
def safe_int(value, default=0):
    try:
        str_value = str(value)
        # 숫자만 추출 (정수 형태만 허용, 소수점 무시)
        match = re.search(r'\d+', str_value)
        if match:
            return int(match.group())
        else:
            return default
    except (ValueError, TypeError):
        return default

# 500툿 넘어가는 길이 자동 분할
def split_message(text, limit=500):
    """문자열을 지정된 길이(limit)로 분할하는 함수"""
    lines = text.split('\n')
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 <= limit:
            current += (line + '\n')
        else:
            chunks.append(current.strip())
            current = line + '\n'
    if current:
        chunks.append(current.strip())
    return chunks

def get_object_particle(word):
    """단어에 맞는 목적격 조사 '을/를' 반환"""
    if not word:
        return '를'
    last_char = word[-1]
    # 유니코드 한글인지 확인
    if not ('가' <= last_char <= '힣'):
        return '를'
    base_code = ord(last_char) - ord('가')
    jongseong = base_code % 28
    return '을' if jongseong != 0 else '를'
        
# 가챠
def handle_gacha(conn, username, content):
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        # 1) 인증 사용자 정보 조회 (소지금)
        cursor.execute("SELECT name, coin FROM auth WHERE name=%s", (username,))
        auth_row = cursor.fetchone()
        if not auth_row:
            print(f"DEBUG: username = '{username}'")
            return f"{username}님은 인증된 사용자가 아닙니다."
        coin = int(auth_row.get('coin', 0))

        # 2) 정산 사용자 정보 조회 (소지품)
        cursor.execute("SELECT name, inventory FROM settlements WHERE name=%s", (username,))
        settle_row = cursor.fetchone()
        if not settle_row:
            print(f"DEBUG: username = '{username}'")
            return f"{username}님은 인증된 사용자가 아닙니다."
        item_name = (settle_row.get('inventory') or '').strip() if settle_row else ''

        # 3) 뽑기 횟수 파싱
        match = re.search(r'(?:\[(?:뽑기|가챠)\]\s*(\d+)?\s*(회|번|연)?|(\d+)\s*(회|번|연)\s*연속?\s*\[(?:뽑기|가챠)\])', content)
        count = int(match.group(1) or match.group(3) or 1)

        if coin < count:
            return f"{username}님, 소지금이 부족합니다. (보유 코인: {coin}, 필요 코인: {count})"

        # 4) 랜덤 아이템 목록 조회
        cursor.execute("SELECT item_name, answer_list FROM gacha WHERE item_name IS NOT NULL AND item_name != ''")
        gacha_rows = cursor.fetchall()

        # 아이템 이름 → 설명 매핑
        gacha_map = {row['item_name']: row.get('answer_list', '') for row in gacha_rows}
        item_pool = list(gacha_map.keys())

        # 랜덤 뽑기
        acquired = random.choices(item_pool, k=count)

        # 결과 메시지 구성 (한 줄: 아이템명 - answer_list)
        result_lines = acquired
        acquired_str = ', '.join(result_lines)
        particle = get_object_particle(result_lines[-1])

        # 기존 소지품에 추가
        new_item_name = item_name + (', ' if item_name else '') + ', '.join(acquired)

        # 5) DB 업데이트: 소지금 차감, 소지품 추가
        cursor.execute("UPDATE auth SET coin = coin - %s WHERE name=%s", (count, username))
        cursor.execute("UPDATE settlements SET inventory = %s WHERE name=%s", (new_item_name, username))

        conn.commit()

    # 최종 출력 메시지
    full_message = f"{username}님, {count}회 가챠를 진행합니다...\n{acquired_str}{particle} 획득하였습니다."
    messages = split_message(full_message)

    return messages


# 아이템 확인
def handle_inventory(conn, username):
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT inventory FROM settlements WHERE name = %s", (username,))
        row = cursor.fetchone()
        if not row:
            return f"{username}님은 인증된 사용자가 아닙니다."
        
        item_name = parse_item_name(row.get('inventory', ''))
        if not item_name:
            return f"{username}님이 획득한 호감도 아이템은 없습니다."
        
        item_counts = Counter(item_name)
        result_lines = [f"{item} x {count}" for item, count in item_counts.items()]
        return f"{username}님이 소지한 아이템 목록은 다음과 같습니다:\n" + '\n'.join(result_lines)


# 아이템 수량 검색
def handle_item_search(conn, username, content):
    match = re.search(r'\[(.+?)\]', content)
    if not match:
        return "검색할 아이템을 [아이템명] 형식으로 입력해주세요."

    search_item = match.group(1)
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT inventory FROM settlements WHERE name = %s", (username,))
        row = cursor.fetchone()
        if not row:
            return f"{username}님은 인증된 사용자가 아닙니다."
        
        item_name = parse_item_name(row.get('inventory', ''))
        count = Counter(item_name).get(search_item, 0)
        if count == 0:
            return f"{username}님은 {search_item}을(를) 가지고 있지 않습니다."
        else:
            return f"{username}님은 {search_item}을(를) {count}개 가지고 있습니다."

# 아이템 매각
def handle_item_sell(conn, username, content):
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # 입력 검증
    matches = re.findall(r'\[([^\[\]]+)\]', content)
    if len(matches) < 2:
        return "[아이템 매각] [아이템명] 형식으로 입력해주세요. 예: [아이템 매각] [연필, 지우개]"

    # 아이템명 리스트 추출
    item_name_to_sell = [item.strip() for item in matches[1].split(',') if item.strip()]
    if not item_name_to_sell:
        return "매각할 아이템이 없습니다."

    # settlement 정보 조회
    cursor.execute("SELECT * FROM settlements WHERE name = %s", (username,))
    settlement_row = cursor.fetchone()
    if not settlement_row:
        return f"{username}님은 등록된 사용자가 아닙니다."

    # auth 정보 조회
    cursor.execute("SELECT * FROM auth WHERE name = %s", (username,))
    auth_row = cursor.fetchone()
    if not auth_row:
        return f"{username}님은 인증된 사용자가 아닙니다."

    # 현재 보유 아이템 파싱
    inventory_str = settlement_row.get('inventory') or ''
    owned_item_name = [item.strip() for item in inventory_str.split(',') if item.strip()]
    owned_counter = Counter(owned_item_name)

    # 기존 매각 대기 아이템 수
    pending_item_name_str = settlement_row.get('sell_pending') or '0'
    pending_item_name = safe_int(pending_item_name_str)

    # 보유 코인
    current_coin = safe_int(auth_row.get('coin', 0))

    # 매각 처리
    sold_item_name = []
    not_owned = []

    for item in item_name_to_sell:
        if owned_counter[item] > 0:
            owned_counter[item] -= 1
            sold_item_name.append(item)
        else:
            not_owned.append(item)

    if not sold_item_name:
        return f"{username}님은 해당 아이템을 소지하고 있지 않습니다."

    # 남은 아이템 문자열 재구성
    updated_item_name = []
    for item, count in owned_counter.items():
        updated_item_name.extend([item] * count)
    updated_inventory_str = ', '.join(updated_item_name)

    # 보상 계산
    sell_bundle_size = 3
    current_sold_count = len(sold_item_name)
    total_sold = pending_item_name + current_sold_count
    total_reward = total_sold // sell_bundle_size
    leftover_item_name = total_sold % sell_bundle_size
    new_coin = current_coin + total_reward

    # DB 업데이트
    cursor.execute(
        "UPDATE settlements SET inventory = %s, sell_pending = %s WHERE name = %s",
        (updated_inventory_str, str(leftover_item_name), username)
    )
    cursor.execute(
        "UPDATE auth SET coin = %s WHERE name = %s",
        (new_coin, username)
    )
    conn.commit()

    # 결과 메시지
    response = (
        f"{username}님이 다음 아이템을 매각하였습니다:\n"
        f"{', '.join(sold_item_name)}\n"
        f"획득 코인: {total_reward}코인\n"
        f"현재 소지 코인: {new_coin}코인"
    )

    if not_owned:
        response += f"\n다음 아이템은 소지하고 있지 않아 매각되지 않았습니다: {', '.join(not_owned)}"

    return response


# 아이템 양도
def handle_gift(conn, giver, content):
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    match = re.search(r'\[(.+?)\]\s*(을|를)\s*\[(.+?)\]\s*에게\s*\[양도\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다. 예: [아이템]을 [받는사람]에게 [양도]"

    item_str = match.group(1)
    receiver = match.group(3)
    item_name_to_give = parse_item_name(item_str)

    # giver 정보 조회
    cursor.execute("SELECT * FROM settlements WHERE name = %s", (giver,))
    giver_row = cursor.fetchone()
    if not giver_row:
        return f"{giver}님은 인증되지 않았습니다."

    # receiver 정보 조회
    cursor.execute("SELECT * FROM settlements WHERE name = %s", (receiver,))
    receiver_row = cursor.fetchone()
    if not receiver_row:
        return f"{receiver}님은 인증되지 않았습니다."

    # 소지품 리스트 파싱
    giver_item_name = parse_item_name(giver_row.get("inventory", ""))
    receiver_item_name = parse_item_name(receiver_row.get("inventory", ""))

    # 아이템 양도 처리
    transferred = []
    not_found = []

    for item in item_name_to_give:
        if item in giver_item_name:
            giver_item_name.remove(item)
            receiver_item_name.append(item)
            transferred.append(item)
        else:
            not_found.append(item)

    # DB 업데이트
    giver_inventory_str = ','.join(giver_item_name)
    receiver_inventory_str = ','.join(receiver_item_name)

    cursor.execute(
        "UPDATE settlements SET inventory = %s WHERE name = %s",
        (giver_inventory_str, giver)
    )
    cursor.execute(
        "UPDATE settlements SET inventory = %s WHERE name = %s",
        (receiver_inventory_str, receiver)
    )
    conn.commit()

    # 결과 메시지 구성
    result = ""
    if transferred:
        result += f"{giver}님이 {receiver}님에게 {', '.join(transferred)}을(를) 양도하였습니다."
    if not_found:
        result += f" {giver}님의 소지품에 없는 아이템입니다: {', '.join(not_found)}"

    return result.strip()


def handle_present(conn, giver, content):
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    # [아이템]을 [받는사람]에게 [선물] 형태 매칭
    match = re.search(r'\[(.+?)\]\s*(을|를|은|는)\s*\[(.+?)\]\s*에게\s*\[(선물)\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다. 예: [아이템]을 [받는사람]에게 [선물]합니다."

    item_str = match.group(1)
    receiver = match.group(3)
    item_name_to_present = parse_item_name(item_str)

    # giver 정보 조회
    cursor.execute("SELECT * FROM settlements WHERE name = %s", (giver,))
    giver_row = cursor.fetchone()
    if not giver_row:
        return f"{giver}님은 인증되지 않았습니다."
    giver_item_name = parse_item_name(giver_row.get('inventory', ''))

    # receiver 정산 정보 확인
    cursor.execute("SELECT * FROM settlements WHERE name = %s", (receiver,))
    receiver_row = cursor.fetchone()
    if not receiver_row:
        return f"{receiver}님은 인증되지 않았습니다."

    # favor 정보 조회
    cursor.execute("SELECT * FROM favor WHERE name = %s", (receiver,))
    favor_row = cursor.fetchone()
    if not favor_row:
        return f"{receiver}님의 호감도 정보가 없습니다."

    # 호감/불호 아이템 파싱
    favor_item_list = parse_item_name(favor_row.get("favor_items", ""))
    disfavor_item_list = parse_item_name(favor_row.get("dislike_items", ""))
    favor_score_str = favor_row.get("favor_score") or "{}"
    favor_status_str = favor_row.get("favor_status") or ""

    try:
        favor_score_dict = json.loads(favor_score_str)
    except json.JSONDecodeError:
        favor_score_dict = {}

    transferred = []
    no_item_name = []
    invalid_items = []

    for item in item_name_to_present:
        if item not in giver_item_name:
            no_item_name.append(item)
            continue
        giver_item_name.remove(item)

        key = f"{giver}_{item}"
        if item in favor_item_list:
            favor_score_dict[giver] = favor_score_dict.get(giver, 0) + 1
            if key not in favor_status_str.split(','):
                if favor_status_str:
                    favor_status_str += ','
                favor_status_str += key
            transferred.append(item)
        elif item in disfavor_item_list:
            favor_score_dict[giver] = favor_score_dict.get(giver, 0) - 1
            transferred.append(item)
        else:
            # 호감도/비호감도 아이템이 아님
            transferred.append(item)
            invalid_items.append(item)

    # giver 소지품 업데이트
    giver_inventory_str = ', '.join(giver_item_name)
    cursor.execute(
        "UPDATE settlements SET inventory = %s WHERE name = %s",
        (giver_inventory_str, giver)
    )

    # favor 점수 및 현황 업데이트
    cursor.execute(
        "UPDATE favor SET favor_score = %s, favor_status = %s WHERE name = %s",
        (json.dumps(favor_score_dict, ensure_ascii=False), favor_status_str, receiver)
    )

    # === complete 열 자동 업데이트 ===
    favor_item_name = [i.strip() for i in favor_row.get('favor_items', '').split(',') if i.strip()]
    favor_status_list = [s.strip() for s in favor_status_str.split(',') if s.strip()]

    # 누가 뭘 줬는지
    name_item_map = {}
    for entry in favor_status_list:
        match = re.match(r'^(.+?)_(.+)$', entry)
        if not match:
            continue
        name_, item_ = match.groups()
        name_item_map.setdefault(name_, set()).add(item_)

    # 모든 favor 아이템을 선물한 사람들 추출
    complete_names = [name_ for name_, item_set in name_item_map.items()
                      if set(favor_item_name).issubset(item_set)]

    complete_str = ', '.join(complete_names)

    cursor.execute(
        "UPDATE favor SET complete = %s WHERE name = %s",
        (complete_str, receiver)
)

    conn.commit()

    # 컴플리트까지 남은 아이템 수 계산
    completed_items = set()
    for entry in favor_status_list:
        match = re.match(r'^(.+?)_(.+)$', entry)
        if match:
            name_, item_ = match.groups()
            if name_ == receiver:
                completed_items.add(item_)

    favor_items_set = set(favor_item_name)
    remaining_items_count = len(favor_items_set - completed_items)

    # 결과 메시지 생성
    result = ""
    if transferred:
        result += f"아이템 선물 성공! {giver}님이 {receiver}님에게 {', '.join(transferred)}을(를) 선물하였습니다."

    if invalid_items:
        result = ""
        result += f"아이템 선물. {giver}님이 {receiver}님에게 {', '.join(transferred)}을(를) 선물하였습니다."
        result += '\n' + ' '.join(
            [f"{item}은(는) {receiver}님이 좋아하는 아이템이 아닙니다." for item in invalid_items]
        )

    if no_item_name:
        result += f"\n선물 실패! {giver}님이 소지하지 않은 호감도 아이템이 있습니다: {', '.join(no_item_name)}"

    return result.strip()
