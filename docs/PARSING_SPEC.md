# 문장 → 트리거 변환 명세

- 최종 업데이트: 2026-11-23
- 상태: `제안` (규칙 목록은 계속 늘려 간다)

사용자가 말하거나 적은 한 문장을 **장소 + 트리거 + 할 일 + 물건 종류**로 변환하는 규칙이다.
처리 순서: **규칙 매칭 → 실패 시 LLM** (`PLAN.md` 8.2).

---

## 1. 표현 → 트리거 규칙

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

규칙에 안 걸리면 LLM으로 넘긴다. LLM도 장소를 못 정하면 확인 카드에서 **장소 블록 선택**을 띄운다.

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
    "place": "home | work | <place_block_id> | null",
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
  "source": "rule | llm_on_device | llm_cloud",
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
  "source": "rule",
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
  "source": "rule",
  "confidence": 1.0
}
```

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
  "source": "rule",
  "confidence": 0.9
}
```

## 6. LLM 프롬프트 지침 (규칙 실패 시)

- 출력은 4장의 JSON만. 설명 문장 금지.
- 사용자의 장소 블록 목록(id, 이름)을 함께 넘겨서 `place`를 그중에서 고르게 한다.
- 장소를 확신할 수 없으면 `place: null`, `confidence` < 0.6 → 앱이 장소 블록 선택을 띄운다.
