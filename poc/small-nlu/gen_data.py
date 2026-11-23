"""합성 학습 데이터 생성기.

한 문장을 만들 때 조각(장소 표현, 물건, 끝말, 군말)을 이어 붙이고,
물건·장소·들를 곳의 글자 위치를 함께 기록해 글자 단위 BIO 태그를 만든다.

라벨
- trigger: arrive | depart | en_route
- anchor : home | work | other   (arrive/depart 는 그 장소, en_route 는 목적지)
- origin : current | home | work | none  (en_route 일 때만)
- action : pick_up | buy | drop_off
- 글자 태그: ITEM(물건), PLACE(집·회사 외 장소 이름), STOP(가는 길에 들를 곳)

anchor=other 인 PLACE 가 사용자 장소 블록이면 custom, 장소 종류 사전에 있으면 near_category 로
앱 쪽에서 후처리한다 (모델은 구분하지 않음).
"""
import json
import random
import sys

R = random.Random(0)

ITEMS_PICKUP = [
    "체육복", "교복", "학회 영수증", "영수증", "우산", "노트북 충전기", "충전기", "도시락통", "텀블러",
    "사원증", "여권", "책", "과제", "리포트", "수영복", "안경", "지갑", "열쇠", "차 키", "서류",
    "도장", "신분증", "보조배터리", "이어폰", "준비물", "실내화", "물통", "수건", "운동화", "노트북",
    "카메라", "삼각대", "USB", "회의 자료", "계약서", "선물", "케이크", "학생증", "필통", "악보",
    "태블릿", "마스크", "핫팩", "장갑", "목도리", "도복", "축구화", "배드민턴 라켓", "요가매트", "등산화",
]
ITEMS_BUY = [
    "물", "생수", "우유", "계란", "휴지", "세제", "두부", "라면", "커피", "과일", "빵", "기저귀",
    "건전지", "샴푸", "치약", "칫솔", "쌀", "김치", "맥주", "콜라", "아이스크림", "고기", "양파",
    "대파", "감기약", "밴드", "소화제", "쓰레기봉투", "종량제 봉투", "물티슈", "고양이 사료", "강아지 간식",
    "꽃", "케이크", "택배 박스", "테이프", "볼펜", "A4 용지", "생리대", "주스",
]
ITEMS_DROP = ["택배 반품", "반품 택배", "편지", "세탁물", "도서관 책", "택배", "우편물", "수선할 옷"]

CUSTOM_PLACES = ["헬스장", "학교", "부모님 댁", "본가", "도서관", "카페", "연구실", "학원", "병원",
                 "수영장", "체육관", "강의실", "어린이집", "유치원", "동아리방", "작업실", "할머니 댁"]
CATEGORIES = ["마트", "편의점", "약국", "다이소", "슈퍼", "우체국", "세탁소", "빵집", "주유소",
              "올리브영", "꽃집", "문구점", "철물점", "이마트", "홈플러스", "동네 마트"]

HANGUL_FREQ = "가나다라마바사아자차카타파하고노도로모보소오조초코토포호구누두루무부수우주추쿠투푸후기니디리미비시이지치키티피히감강건경관국군금길김남단당대동라락란량력로록론류리림만명문민박반방배백범별병보복본봉부북분빈산상새서석선설성세소손송수순숭승시신실심안양어언엄여연영예오옥온완왕용우운원월위유윤은음이익인일임자작장재전정제조종주준중지진찬창채천철청초최춘충태택판평포표하학한함항해행향허헌현형혜호홍화환황회효훈휘희"


MODIFIERS = ["여름", "새", "작은", "큰", "빨간", "파란", "내", "아이", "운동", "주말", "여행", "예비",
             "휴대용", "접이식", "흰", "검은", "엄마", "아빠", "동생"]


def pseudo_word():
    n = R.choice([1, 2, 2, 2, 3, 3, 4])
    return "".join(R.choice(HANGUL_FREQ) for _ in range(n))


def pseudo_noun():
    r = R.random()
    if r < 0.35:  # 띄어쓴 복합 명사: "가나 다라"
        return pseudo_word() + " " + pseudo_word()
    return pseudo_word()


def pick_item(action):
    if R.random() < 0.25:
        return pseudo_noun()
    if R.random() < 0.12:  # 꾸밈말 + 실제 물건: "여름 이불", "새 충전기"
        return R.choice(MODIFIERS) + " " + R.choice(ITEMS_PICKUP + ITEMS_BUY)
    return R.choice({"pick_up": ITEMS_PICKUP, "buy": ITEMS_BUY, "drop_off": ITEMS_DROP}[action])


ENDINGS = {
    "pick_up": ["", "", "", "챙기기", "챙겨", "챙기자", "챙겨야 함", "챙겨야지", "챙깁시다", "챙겨요", "챙길 것",
                "기억", "기억해", "기억해줘", "잊지 말기", "까먹지 말기", "까먹지마", "알려줘", "가져가기",
                "가져와", "가져오기", "들고 가기", "들고 와", "꼭", "꼭 챙기기", "챙겨 놓기", "빼놓기", "넣어두기"],
    "buy": ["", "", "사기", "사 오기", "사오기", "사가기", "사야 함", "사야지", "삽시다", "사자", "구매", "사 와",
            "사 와줘", "사기 기억", "사는 거 잊지 말기", "꼭 사기", "좀 사기", "하나 사기", "사 놓기", "알려줘"],
    "drop_off": ["", "보내기", "부치기", "맡기기", "반납", "반납하기", "갖다 놓기", "갖다주기", "맡기자", "보내야 함",
                 "찾기", "찾아오기", "부치자", "꼭 보내기"],
}
PARTICLE = {"pick_up": ["", "", "을", "를"], "buy": ["", "", "", "을", "를"], "drop_off": ["", "", "을", "를"]}
_DAY = ["", "", "내일 ", "오늘 ", "모레 ", "이따 ", "이따가 ", "금요일 "]
_TIME = ["", "", "", "아침 ", "아침에 ", "저녁 ", "저녁에 ", "밤에 ", "점심때 "]
_FILL = ["", "", "", "", "아 맞다 ", "꼭 ", "잊지 말고 ", "음 "]
PREFIX = [f + d + t for f in _FILL for d in _DAY for t in _TIME]
SUFFIX = ["", "", "", "", "!", ".", "!!", " 꼭", " ㅎㅎ"]

# 장소 표현: (문자열 템플릿, trigger, anchor). {P} 는 PLACE 자리
PLACE_EXPR = [
    ("집에서", "arrive", "home"), ("집에 가면", "arrive", "home"), ("집 가면", "arrive", "home"),
    ("집에 도착하면", "arrive", "home"), ("집 도착하면", "arrive", "home"), ("집 들어가면", "arrive", "home"),
    ("집에 들어가서", "arrive", "home"), ("귀가하면", "arrive", "home"), ("귀가해서", "arrive", "home"),
    ("집에 오면", "arrive", "home"), ("집 오면", "arrive", "home"), ("집에 가서", "arrive", "home"),
    ("집 가서", "arrive", "home"), ("집 도착해서", "arrive", "home"), ("집 와서", "arrive", "home"),
    ("집에 오자마자", "arrive", "home"), ("집 들어가자마자", "arrive", "home"), ("집에 있을 때", "arrive", "home"),
    ("집 가면은", "arrive", "home"), ("집가면", "arrive", "home"),
    ("집 나갈 때", "depart", "home"), ("집에서 나갈 때", "depart", "home"), ("나가기 전에", "depart", "home"),
    ("나갈 때", "depart", "home"), ("출근할 때", "depart", "home"), ("출근하기 전에", "depart", "home"),
    ("집 나서면서", "depart", "home"), ("외출할 때", "depart", "home"), ("집 나가기 전에", "depart", "home"),
    ("현관 나갈 때", "depart", "home"), ("등교할 때", "depart", "home"), ("나가면서", "depart", "home"),
    ("회사에서", "arrive", "work"), ("회사 가면", "arrive", "work"), ("회사 도착하면", "arrive", "work"),
    ("출근하면", "arrive", "work"), ("출근해서", "arrive", "work"), ("사무실 가면", "arrive", "work"),
    ("사무실 도착하면", "arrive", "work"), ("회사 가서", "arrive", "work"), ("회사 도착해서", "arrive", "work"),
    ("사무실에서", "arrive", "work"), ("회사에 가면", "arrive", "work"),
    ("퇴근할 때", "depart", "work"), ("퇴근하면서", "depart", "work"), ("퇴근 전에", "depart", "work"),
    ("회사 나올 때", "depart", "work"), ("회사에서 나갈 때", "depart", "work"), ("퇴근하기 전에", "depart", "work"),
    ("사무실 나갈 때", "depart", "work"), ("퇴근 직전에", "depart", "work"), ("회사 나서면서", "depart", "work"),
    ("{P}에서", "arrive", "other"), ("{P} 가면", "arrive", "other"), ("{P} 도착하면", "arrive", "other"),
    ("{P} 가서", "arrive", "other"), ("{P}에 가면", "arrive", "other"), ("{P} 들르면", "arrive", "other"),
    ("다음에 {P} 가면", "arrive", "other"), ("{P} 지나가면", "arrive", "other"), ("{P} 보이면", "arrive", "other"),
    ("{P} 들러서", "arrive", "other"), ("{P}에 도착하면", "arrive", "other"),
    ("{P}에서 나올 때", "depart", "other"), ("{P} 나갈 때", "depart", "other"), ("{P} 끝나고 나올 때", "depart", "other"),
]
# 가는 길에: (템플릿, anchor=목적지, origin). {P}=목적지 이름
ROUTE_EXPR = [
    ("집에 가는 길에", "home", "current"), ("집 가는 길에", "home", "current"), ("퇴근길에", "home", "work"),
    ("퇴근하는 길에", "home", "work"), ("집 오는 길에", "home", "current"), ("귀갓길에", "home", "current"),
    ("들어가는 길에", "home", "current"), ("집에 들어가는 길에", "home", "current"), ("퇴근길", "home", "work"),
    ("집 가면서", "home", "current"), ("집에 가면서", "home", "current"), ("퇴근하고 집 가는 길에", "home", "work"),
    ("회사 가는 길에", "work", "current"), ("출근길에", "work", "home"), ("출근하는 길에", "work", "home"),
    ("회사 가면서", "work", "current"), ("출근길", "work", "home"),
    ("{P} 가는 길에", "other", "current"), ("{P}에 가는 길에", "other", "current"), ("{P} 가면서", "other", "current"),
]
STOP_EXPR = ["{S}에서 ", "{S} 들러서 ", "{S} 들러 ", "{S}에 들러서 ", "{S} 가서 "]


def build(pieces):
    """pieces: [(text, tag or None)] -> text, char tags"""
    text, tags = "", []
    for t, tag in pieces:
        for i, _ in enumerate(t):
            if tag is None:
                tags.append("O")
            else:
                tags.append(("B-" if i == 0 else "I-") + tag)
        text += t
    return text, tags


def expr_pieces(tmpl, place):
    if "{P}" not in tmpl:
        return [(tmpl, None)]
    a, b = tmpl.split("{P}")
    return [(a, None), (place, "PLACE"), (b, None)]


def sample():
    action = R.choices(["pick_up", "buy", "drop_off"], [0.5, 0.38, 0.12])[0]
    item = pick_item(action)
    ending = R.choice(ENDINGS[action])
    particle = R.choice(PARTICLE[action]) if ending else ""
    if particle in ("을", "를") and "가" <= item[-1] <= "힣":
        particle = "을" if (ord(item[-1]) - 0xAC00) % 28 else "를"
    rec = {"trigger": None, "anchor": None, "origin": "none", "action": action,
           "item": item, "place": None, "stop": None}

    route = R.random() < 0.28
    if route:
        tmpl, anchor, origin = R.choice(ROUTE_EXPR)
        place = R.choice(CUSTOM_PLACES) if "{P}" in tmpl else None
        rec.update(trigger="en_route", anchor=anchor, origin=origin, place=place)
        head = expr_pieces(tmpl, place) + [(" ", None)]
        if R.random() < 0.55 or action == "buy" and R.random() < 0.3:
            s = R.choice(CATEGORIES)
            st = R.choice(STOP_EXPR)
            a, b = st.split("{S}")
            head += [(a, None), (s, "STOP"), (b, None)]
            rec["stop"] = s
    else:
        cands = PLACE_EXPR
        if action == "buy":  # 사는 일은 장소 종류가 자연스러움
            cands = [e for e in PLACE_EXPR if e[2] == "other"] if R.random() < 0.6 else PLACE_EXPR
        tmpl, trig, anchor = R.choice(cands)
        place = None
        if "{P}" in tmpl:
            place = R.choice(CATEGORIES if action == "buy" or R.random() < 0.4 else CUSTOM_PLACES)
        rec.update(trigger=trig, anchor=anchor, place=place)
        head = expr_pieces(tmpl, place) + [(" ", None)]

    body = [(item, "ITEM"), (particle, None)] + ([(" " + ending, None)] if ending else [])
    pre, suf = R.choice(PREFIX), R.choice(SUFFIX)
    if R.random() < 0.22:  # 어순 뒤집기: "체육복 집에서"
        head_tail = [(t, g) for t, g in head]
        head_tail[-1] = ("", None)
        pieces = [(pre, None), (item, "ITEM"), (particle + " ", None)] + head_tail
        if ending:
            pieces += [(" " + ending, None)]
    else:
        pieces = [(pre, None)] + head + body
    pieces += [(suf, None)]
    text, tags = build(pieces)
    if R.random() < 0.15:  # 띄어쓰기 생략 노이즈
        keep = [(c, t) for c, t in zip(text, tags) if c != " " or R.random() < 0.3]
        text = "".join(c for c, _ in keep)
        tags = [t for _, t in keep]
    # 앞뒤 공백 정리
    while text.startswith(" "):
        text, tags = text[1:], tags[1:]
    while text.endswith(" "):
        text, tags = text[:-1], tags[:-1]
    rec.update(text=text, tags=tags)
    return rec


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    out = sys.argv[2] if len(sys.argv) > 2 else "train.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for _ in range(n):
            f.write(json.dumps(sample(), ensure_ascii=False) + "\n")
