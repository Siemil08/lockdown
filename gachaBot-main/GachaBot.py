from mastodon import Mastodon, StreamListener
import gspread
from google.oauth2.service_account import Credentials
from collections import Counter
import random
import re
import json

# ====== 마스토돈 인증 ======
# 봇으로 사용하려는 마스토돈 계정에 따라 발급바독 바꾸기
mastodon = Mastodon(
    client_id='zA3oVHYtYo3wQV4WkhX_CcspWuLQJ2Cu6C-e5FB8cpE',
    client_secret='pREfQ3w9U553QeTQG74RJoKoEWM3RuKrXRFfd2P20Lg',
    access_token='vmZSeRuIiYWYSthApqaayGfPhENlZtGPt7hxKDOkZh4', # 이거 권한 수정할 때마다 토큰이 바뀜 주의
    api_base_url='https://mastodon.social'
)

# ====== 구글 시트 인증 ======
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('service_account.json', scopes=scope)
gc = gspread.authorize(creds)

# ====== 시트 연결 ======
sheet_key = '1gF10CYj794dZtHdepRz-78VgpUEWlweKX6bEfA3Fa8w'
auth_ws = gc.open_by_key(sheet_key).worksheet('인증')
random_ws = gc.open_by_key(sheet_key).worksheet('가챠')

# ====== 유틸 ======
def get_column_index(ws, column_name):
    headers = ws.row_values(1)
    return headers.index(column_name) + 1

def clean_html_tags(text):
    return re.sub(r'<[^>]+>', '', text).strip()

def parse_items(text):
    return [i.strip() for i in re.split(r'[,\s]+', text) if i.strip()]

# ====== 정산 기능 ======
def handle_balance(username):
    # 사용자 정보 가져오기
    accounts = mastodon.account_search(username, limit=1)
    user_info = accounts[0]
    tweet_count = user_info['statuses_count']  # 트윗 수
    
    records = auth_ws.get_all_records()
    for row in records:
        if row['Name'] == username:
            return f"{username}님의 현재 소지금은 {row['소지금']}코인입니다."
    return f"{username}님은 인증된 사용자가 아닙니다."

def handle_present(giver, content):
    # [아이템]을 [받는사람]에게 [선물]
    match = re.search(r'\[(.+?)\]\s*(을|를|은|는)\s*\[(.+?)\]\s*에게\s*\[(선물)\]', content)
    if not match:
        return ("입력 형식이 올바르지 않습니다. 반드시 입력순서를 지켜주시기 바랍니다.\n"
                "예: [아이템]을 [받는사람]에게 [선물]")

    item_str = match.group(1)
    receiver = match.group(3)
    items_to_present = parse_items(item_str)

    # '인증' 시트 데이터 가져오기
    auth_records = auth_ws.get_all_records()
    giver_idx, receiver_idx = None, None
    giver_items = []

    for i, row in enumerate(auth_records):
        if row['Name'].strip() == giver.strip():
            giver_idx = i + 2
            giver_items = parse_items(row.get('소지품', ''))
        if row['Name'].strip() == receiver.strip():
            receiver_idx = i + 2

    if giver_idx is None:
        return f"{giver}님은 인증된 사용자가 아닙니다."
    if receiver_idx is None:
        return f"{receiver}님은 인증된 사용자가 아닙니다."

    # '호감도' 시트 데이터 가져오기
    favor_ws = gc.open_by_key(sheet_key).worksheet('호감도')
    favor_records = favor_ws.get_all_records()
    favor_idx = None
    favor_col = get_column_index(favor_ws, '호감점수')
    favor_item_col = get_column_index(favor_ws, '호감도 현황')
    favor_name_col = get_column_index(favor_ws, 'Name')

    for i, row in enumerate(favor_records):
        if row['Name'].strip() == receiver.strip():
            favor_idx = i + 2
            break

    if favor_idx is None:
        return f"{receiver}님의 호감도 데이터가 없습니다."

    # '호감 아이템'과 '불호 아이템' 리스트
    favor_item_list = [i.strip() for i in favor_ws.acell('B2').value.split(',')]  # 예: B열에 호감 아이템 목록이 있다고 가정
    disfavor_item_list = [i.strip() for i in favor_ws.acell('C2').value.split(',')]  # C열에 불호 아이템 목록

    # 호감점수 딕셔너리 파싱
    favor_score_str = favor_ws.cell(favor_idx, favor_col).value or '{}'
    try:
        favor_score_dict = json.loads(favor_score_str)
    except:
        favor_score_dict = {}

    # 호감도 현황 문자열 불러오기
    favor_status_str = favor_ws.cell(favor_idx, favor_item_col).value or ''

    transferred = []
    no_items = []

    for item in items_to_present:
        if item not in giver_items:
            no_items.append(item)
            continue
        # 선물한 아이템은 giver 소지품에서 제거
        giver_items.remove(item)

        # 점수 및 현황 처리
        key = f"{giver}_{item}"
        if item in favor_item_list:
            # 호감 아이템 -> 점수 +1, 중복 체크 후 현황 추가
            favor_score_dict[giver] = favor_score_dict.get(giver, 0) + 1
            if key not in favor_status_str:
                if favor_status_str:
                    favor_status_str += ', '
                favor_status_str += key
            transferred.append(item)
        elif item in disfavor_item_list:
            # 불호 아이템 -> 점수 -1, 중복 체크 후 현황 추가
            favor_score_dict[giver] = favor_score_dict.get(giver, 0) - 1
            transferred.append(item)
        else:
            # 호감도 아이템도 불호 아이템도 아닌 경우 점수 변동 없음, 아이템은 소진됨
            transferred.append(item)

    # 업데이트: giver 소지품
    item_col_auth = get_column_index(auth_ws, '소지품')
    auth_ws.update_cell(giver_idx, item_col_auth, ', '.join(giver_items))

    # 업데이트: 호감도 시트 점수 및 현황 (ensure_ascii=False 추가)
    favor_ws.update_cell(favor_idx, favor_col, json.dumps(favor_score_dict, ensure_ascii=False))
    favor_ws.update_cell(favor_idx, favor_item_col, favor_status_str)

    # === 컴플리트 열 자동 업데이트 ===
    favor_items_col = get_column_index(favor_ws, '호감 아이템')
    complete_col = get_column_index(favor_ws, '컴플리트')
    favor_items_str = favor_ws.cell(favor_idx, favor_items_col).value or ''
    favor_items = [i.strip() for i in favor_items_str.split(',') if i.strip()]
    favor_status_list = [s.strip() for s in favor_status_str.split(',') if s.strip()]

    name_item_map = {}
    for entry in favor_status_list:
        match = re.match(r'^(.+?)_(.+)$', entry)
        if not match:
            continue
        name, item = match.groups()
        if name not in name_item_map:
            name_item_map[name] = set()
        name_item_map[name].add(item)

    complete_names = []
    for name, item_set in name_item_map.items():
        if all(favor_item in item_set for favor_item in favor_items):
            complete_names.append(name)

    favor_ws.update_cell(favor_idx, complete_col, ', '.join(complete_names))

    result = ""
    if transferred:
        result += f"{giver}님이 {receiver}님에게 {', '.join(transferred)}을(를) 선물하였습니다.\n"
        for name, score in favor_score_dict.items():
            result += f"{name}님의 현재 호감도 : {score}\n"
    if no_items:
        result += f"{giver}님의 소지품에 없는 아이템이 있습니다: {', '.join(no_items)}"

    return result.strip()

# ====== 코인 양도 기능 ======
def handle_coin_transfer(giver, content):
    match = re.search(r'\[코인\s*양도\]\s*\[([^\[\]]+)\]\s*\[(\d+)\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다.\n예: [코인 양도] [받는 사람] [10]"

    receiver = match.group(1).strip()
    amount = int(match.group(2))

    auth_records = auth_ws.get_all_records()
    giver_idx, receiver_idx = None, None

    for i, row in enumerate(auth_records):
        if row['Name'] == giver.strip():
            giver_idx = i + 2
            giver_coin = int(row.get('소지금', 0))
        if row['Name'] == receiver.strip():
            receiver_idx = i + 2
            receiver_coin = int(row.get('소지금', 0))

    if giver_idx is None:
        return f"{giver}님은 인증된 사용자가 아닙니다."
    if receiver_idx is None:
        return f"{receiver}님은 인증된 사용자가 아닙니다."
    if giver_coin < amount:
        return f"{giver}님의 소지금이 부족합니다. 현재 소지금: {giver_coin}코인"

    # 코인 업데이트
    auth_ws.update_cell(giver_idx, get_column_index(auth_ws, '소지금'), giver_coin - amount)
    auth_ws.update_cell(receiver_idx, get_column_index(auth_ws, '소지금'), receiver_coin + amount)

    return f"{giver}님이 {receiver}님에게 {amount}코인을 양도하였습니다."

# ====== 코인 획 기능 ======
def handle_coin_gain(username, content):
    match = re.search(r'\[코인\s*획득\]\s*\[(\d+)\]', content)
    if not match:
        return "입력 형식이 올바르지 않습니다.\n예: [코인 획득] [5]"

    amount = int(match.group(1))

    auth_records = auth_ws.get_all_records()
    user_idx = None
    for i, row in enumerate(auth_records):
        if row['Name'] == username.strip():
            user_idx = i + 2
            current_coin = int(row.get('소지금', 0))
            break

    if user_idx is None:
        return f"{username}님은 인증된 사용자가 아닙니다."

    # 코인 합산
    new_coin = current_coin + amount
    auth_ws.update_cell(user_idx, get_column_index(auth_ws, '소지금'), new_coin)

    deposit_sheet_key = '1LVTv2lvjvRcksZFo8sTY6Fr-y_kVYdHUIsz7VgSbx3g'
    deposit_ws = gc.open_by_key(deposit_sheet_key).worksheet('봇입금') 

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"{username}님이 {amount}코인을 획득하였습니다. (누적: {new_coin}코인)"
    deposit_ws.append_row([timestamp, log_message])

    return log_message


# ====== 가챠 기능 ======
def handle_gacha(username, content):
    records = auth_ws.get_all_records()
    for idx, row in enumerate(records):
        if row['Name'] == username:
            row_idx = idx + 2
            coin = int(row['소지금'])
            items = row.get('소지품', '').strip()

            # 연속 여부 파악
            match = re.search(r'\[가챠\]\s*(\d+)?\s*(연속|연)?', content)
            count = 1
            is_continuous = False
            if match:
                if match.group(1):
                    count = int(match.group(1))
                if match.group(2):
                    is_continuous = True

            if coin < count:
                return f"{username}님, 소지금이 부족합니다. (보유 코인: {coin}, 필요 코인: {count})"

            # 랜덤 리스트 가져오기
            gacha_rows = random_ws.get_all_records()
            item_pool = []
            for r in gacha_rows:
                if '답변 리스트' in r and r['답변 리스트'].strip():
                    item_pool.extend([i.strip() for i in r['답변 리스트'].split(',')])

            # 아이템 뽑기 및 결과 저장
            acquired = random.choices(item_pool, k=count)
            new_items = items + (', ' if items else '') + ', '.join(acquired)

            # 시트 업데이트
            coin_col = get_column_index(auth_ws, '소지금')
            item_col = get_column_index(auth_ws, '소지품')
            auth_ws.update_cell(row_idx, coin_col, coin - count)
            auth_ws.update_cell(row_idx, item_col, new_items)

            if is_continuous:
                return f"{username}님이 {count}회 연속 가챠를 진행하여 {', '.join(acquired)}을(를) 획득했습니다!"
            else:
                if count == 1:
                    return f"{username}은(는) {acquired[0]}을(를) 획득했습니다."
                else:
                    return f"{username}은(는) {', '.join(acquired)}을(를) 획득했습니다."
              
    return f"{username}님은 인증된 사용자가 아닙니다."

# ====== 소지품 확인 기능능 ======
def handle_inventory(username):
    records = auth_ws.get_all_records()
    for row in records:
        if row['Name'] == username:
            items = parse_items(row.get('소지품', ''))
            if not items:
                return f"{username}님이 획득한 호감도 아이템은 현재 없습니다."
            item_counts = Counter(items)
            result_lines = [f"{item} x {count} " for item, count in item_counts.items()]
            return f"{username}님이 획득한 호감도 아이템은 다음과 같습니다. \n" + '\n'.join(result_lines)
    return f"{username}님은 인증된 사용자가 아닙니다."

# ====== 아이템 검색 기능 ======
def handle_item_search(username, content):
    match = re.search(r'\[(.+?)\]', content)
    if not match:
        return "검색할 아이템을 []로 감싸서 입력해 주세요."

    search_item = match.group(1)

    records = auth_ws.get_all_records()
    for row in records:
        if row['Name'] == username:
            items = parse_items(row.get('소지품', ''))
            item_counts = Counter(items)
            count = item_counts.get(search_item, 0)
            if count == 0:
                return f"{username}님은 [{search_item}]을(를) 가지고 있지 않습니다."
            else:
                return f"{username}님은 [{search_item}]을(를) {count}개 가지고 있습니다."
    return f"{username}님은 인증된 사용자가 아닙니다."

# ====== 양도 기능 ======

def handle_gift(giver, content):
    # [아이템]을/를 [받는사람]에게 [양도]
    match = re.search(r'\[(.+?)\]\s*(을|를|은|는)\s*\[(.+?)\]\s*에게\s*\[(양도)\]', content)
    if not match:
        return ("입력 형식이 올바르지 않습니다. 반드시 입력순서를 지켜주시기 바랍니다.\n"
                "예: [아이템]을 [받는사람]에게 [양도]")

    item_str = match.group(1)
    receiver = match.group(3)

    items_to_give = parse_items(item_str)

    auth_records = auth_ws.get_all_records()
    giver_idx, receiver_idx = None, None
    giver_items, receiver_items = [], []
    
    for i, row in enumerate(auth_records):
        if row['Name'].strip() == giver.strip():
            giver_idx = i + 2
            giver_items = parse_items(row.get('소지품', ''))
        if row['Name'].strip() == receiver.strip():
            receiver_idx = i + 2
            receiver_items = parse_items(row.get('소지품', ''))

    if giver_idx is None:
        return f"{giver}님은 인증된 사용자가 아닙니다."
    if receiver_idx is None:
        return f"{receiver}님은 인증된 사용자가 아닙니다."

    transferred = []
    not_found = []

    # 양도 가능한 아이템 처리
    for item in items_to_give:
        if item in giver_items:
            giver_items.remove(item)
            receiver_items.append(item)
            transferred.append(item)
        else:
            not_found.append(item)

    # 업데이트
    item_col = get_column_index(auth_ws, '소지품')
    auth_ws.update_cell(giver_idx, item_col, ', '.join(giver_items))
    auth_ws.update_cell(receiver_idx, item_col, ', '.join(receiver_items))

    result = ""
    if transferred:
        result += f"{giver}님이 {receiver}님에게 {', '.join(transferred)}을(를) 양도하였습니다.\n"
    if not_found:
        result += f"{giver}님의 소지품에 해당 물품이 없습니다: {', '.join(not_found)}"

    return result.strip()

# ====== 마스토돈 리스너 ======
class GachaBotListener(StreamListener):
    def on_notification(self, notification):
        if notification['type'] == 'mention':
            content_html = notification['status']['content']
            content = clean_html_tags(content_html)
            username = notification['account']['display_name'].strip()
            acct = notification['account']['acct']
            status_id = notification['status']['id']

            print(f"[MENTION] {username}: {content}")

            content_lower = content.lower()

            if '[정산]' in content_lower:
                reply = handle_balance(username)
            elif '[가챠]' in content_lower:
                reply = handle_gacha(username, content)
            elif '[소지품]' in content_lower or '[인벤토리]' in content_lower:
                reply = handle_inventory(username)
            elif '[양도]' in content_lower :
                # handle_gift는 giver와 content가 필요하므로 username과 원문 content 그대로 전달
                reply = handle_gift(username, content)
            elif re.search(r'\[.+?\].*(몇 개|수량)', content_lower):
                reply = handle_item_search(username, content)
            elif '[선물]' in content_lower:
                reply = handle_present(username, content)
            elif '[코인 양도]' in content:
                result = handle_coin_transfer(username, content)
            elif '[코인 획득]' in content:
                result = handle_coin_gain(username, content)
            else:
                return  # 처리하지 않는 멘션 무시

            mastodon.status_post(
                status=f"@{acct} {reply}",
                in_reply_to_id=status_id,
                visibility='unlisted'
            )

# ====== 실행 ======
if __name__ == '__main__':
    print("🎁 GachaBot 실행 중...")
    mastodon.stream_user(GachaBotListener())
