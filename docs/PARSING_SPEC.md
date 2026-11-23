# 문장 → 트리거 변환 명세

- 최종 업데이트: 2026-11-23
- 상태: LLM 중심 해석 `확정` / 세부 구조 `제안`

사용자가 말하거나 적은 한 문장을 **장소 + 트리거 + 할 일 + 물건 종류**로 변환하는 명세다.

---

## 0. 처리 구조 — LLM이 기본 해석기

규칙만으로는 사람들의 표현을 다 처리할 수 없다 (`확정`, 2026-11-23).

| 변형 위치 | 예시 | 처리 |
|---|---|---|
| 끝말 | 교복 챙기자 / 교복 챙겨 / 교복 기억 / 교복 챙깁시다 | 해석하지 않는다. 할 일 핵심어("교복")만 뽑고 원문은 `raw_text`로 보관 |
| 장소·시점 | 집 도착하면 / 집 들어가서 / 귀가하면 / 저녁에 집에서 / 이따 집 가서 | **LLM이 해석** (규칙으로는 끝이 없음) |
| 순서 | "교복 집에서" / "집에서 교복" | LLM이 해석 |

처리 순서 (`제안`):

1. **사용자 표현 캐시**: 이 사용자가 전에 쓴 표현 패턴과 같으면 즉시 처리 (예: "귀가하면" → 이전에 home/arrive로 확정됨)
2. **LLM 해석 (기본)**: 기기 내장 LLM → 미지원 기기는 클라우드 LLM. 출력은 4장 JSON
3. **오프라인 규칙 (보조)**: 네트워크·기기 LLM 모두 없을 때만 1장 기준표로 최소한 처리
4. **확인 카드**: 결과 표시. 장소를 못 정하면(`place: null` 또는 `confidence` < 0.6) 장소 블록 선택
5. **학습**: 사용자가 확인 카드를 고치지 않고 저장하면 그 표현 → 결과를 1번 캐시에 추가

LLM 응답 지연(약 1초 내외)은 확인 카드가 뜨는 동안 처리되므로 사용자 체감 부담이 작다.

---

## 1. 트리거 의미 기준표

LLM 프롬프트의 기준 예시이자, 오프라인 규칙의 최소 목록이다. **모든 표현을 나열하는 표가 아니다.**
`○○`는 할 일(물건)이다.

| 표현 | trigger.type | 장소 | 비고 |
|---|---|---|---|
| 집에서 ○○ / 집 가면 ○○ / 집에 오면 ○○ / 집 도착하면 ○○ | `arrive` | home | 물건 챙기기면 재알림 적용 (3장) |
| 집 나갈 때 ○○ / 나가면서 ○○ / 출근할 때 ○○ | `depart` | home | |
| 회사에서 ○○ / 출근하면 ○○ / 회사 가면 ○○ | `arrive` | work | |
| 퇴근할 때 ○○ / 퇴근하면서 ○○ | `depart` | work | |
| 퇴근길에 ○○ | `en_route` | work → home | 들를 곳은 물건에서 추론 |
| ○○ 가는 길에 △△ (예: 집에 가는 길에 물) | `en_route` | current → ○○ | 들를 곳은 물건에서 추론 |
| 퇴근길에 마트에서 ○○ | `en_route` | work → home | 들를 곳 = mart (직접 지정) |
| 마트에서 ○○ / 편의점 들러서 ○○ / 다음에 약국 가면 ○○ | `near_category` | 해당 종류 | |
| {사용자 추가 장소}에서 ○○ | `arrive` | 해당 장소 블록 | 예: 헬스장에서 수건 |

LLM도 장소를 못 정하면 확인 카드에서 **장소 블록 선택**을 띄운다.

### 1.1 장소가 없거나 "지금 이곳"을 뜻하는 경우 — `제안`

| 표현 | trigger.type | 장소 | 비고 |
|---|---|---|---|
| 나갈 때 ○○ / 나가면서 ○○ / 일어날 때 ○○ | `depart` | `null` (앱이 지금 위치로 결정) | `PLAN.md` 5.4 장소 결정 규칙 |
| 카페 나갈 때 ○○ / 여기서 나갈 때 ○○ | `depart` | `current` | 장소 종류 이름이어도 "지금 이 가게" 뜻 |

- 해석 모델은 "나갈 때"를 집으로 단정하지 않는다. 집인지 임시 장소인지는 **지금 위치**를 아는 앱이 정한다.
- `trigger.place`에 `current` 값을 추가한다 (4장 스키마).

## 2. 물건 → 행동·들를 곳 매핑

| 물건 예시 | item_category | action | 들를 곳 (en_route 기본값) |
|---|---|---|---|
| 체육복, 옷 | clothing | `pick_up` | — |
| 영수증, 서류 | document | `pick_up` | — |
| 우산 | umbrella | `pick_up` (집·회사) / `buy` (가는 길에) | convenience_store |
| 물, 음료 | drink | `buy` | convenience_store, mart |
| 약 | medicine | `buy` | pharmacy |
| 택배 반품 | parcel | `drop_off` | convenience_store, post_office |

- `pick_up`: 장소에 있는 물건을 챙김
- `buy`: 사 와야 함 → 들를 곳이 필요
- `drop_off`: 가져다 놓아야 함
- 표에 없는 물건은 LLM이 분류한다. 자주 나오는 것은 표에 추가한다.

## 3. 기본 재알림 규칙

| 조건 | 재알림 |
|---|---|
| action = `pick_up`, trigger = `arrive` (home) | 미완료 시 다음 `depart` (home) 때 |
| trigger = `en_route`, 목적지 도착까지 미완료 | 다음날 같은 경로 출발 때 (사용자에게 "다시 알려줄게?" 확인) |

## 4. 출력 JSON 스키마

```json
{
  "raw_text": "string — 원문",
  "task": "string — 할 일 (예: 체육복)",
  "item_category": "clothing | document | umbrella | drink | medicine | parcel | other",
  "action": "pick_up | buy | drop_off | do",
  "trigger": {
    "type": "arrive | depart | near_category | en_route",
    "place": "home | work | current | <place_block_id> | null",
    "category": "convenience_store | mart | pharmacy | post_office | null",
    "en_route": {
      "origin": "current | home | work | <place_block_id>",
      "destination": "home | work | <place_block_id>",
      "stop_categories": ["convenience_store"],
      "last_chance_radius_m": 500
    }
  },
  "followup": {
    "re_alert_on": "next_depart | next_same_route | none"
  },
  "source": "user_cache | llm_on_device | llm_cloud | offline_rule",
  "confidence": 0.0
}
```

`trigger.en_route`는 type이 `en_route`일 때만 채운다. 나머지는 `null`.

## 5. 예시

### "집에서 체육복"
```json
{
  "raw_text": "집에서 체육복",
  "task": "체육복",
  "item_category": "clothing",
  "action": "pick_up",
  "trigger": { "type": "arrive", "place": "home", "category": null, "en_route": null },
  "followup": { "re_alert_on": "next_depart" },
  "source": "llm_on_device",
  "confidence": 1.0
}
```

### "퇴근할 때 우산"
```json
{
  "raw_text": "퇴근할 때 우산",
  "task": "우산",
  "item_category": "umbrella",
  "action": "pick_up",
  "trigger": { "type": "depart", "place": "work", "category": null, "en_route": null },
  "followup": { "re_alert_on": "none" },
  "source": "llm_on_device",
  "confidence": 1.0
}
```

### "카페 나갈 때 우산" (지금 카페에 머무는 중)
```json
{
  "raw_text": "카페 나갈 때 우산",
  "task": "우산",
  "item_category": "umbrella",
  "action": "pick_up",
  "trigger": { "type": "depart", "place": "current", "category": null, "en_route": null },
  "followup": { "re_alert_on": "none" },
  "source": "llm_on_device",
  "confidence": 0.9
}
```
앱 처리: 지금 좌표로 임시 장소 생성 → `PLAN.md` 5.4 알림 단계.

### "집에 가는 길에 물"
```json
{
  "raw_text": "집에 가는 길에 물",
  "task": "물",
  "item_category": "drink",
  "action": "buy",
  "trigger": {
    "type": "en_route",
    "place": null,
    "category": null,
    "en_route": {
      "origin": "current",
      "destination": "home",
      "stop_categories": ["convenience_store", "mart"],
      "last_chance_radius_m": 500
    }
  },
  "followup": { "re_alert_on": "next_same_route" },
  "source": "llm_on_device",
  "confidence": 0.9
}
```

## 6. LLM 프롬프트 지침 (기본 해석 경로)

- 출력은 4장의 JSON만. 설명 문장 금지.
- `task`에는 끝말을 뺀 핵심어만 넣는다: "교복 챙기자", "교복 기억", "교복 챙깁시다" → 모두 `"task": "교복"`.
- 1장 기준표와 5장 예시를 few-shot 예시로 넣는다.
- 사용자의 장소 블록 목록(id, 이름)을 함께 넘겨서 `place`를 그중에서 고르게 한다.
- 장소를 확신할 수 없으면 `place: null`, `confidence` < 0.6 → 앱이 장소 블록 선택을 띄운다.
