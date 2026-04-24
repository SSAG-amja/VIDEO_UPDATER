import re


def normalize_compare_text(value) -> str:
    if value is None:
        return ""

    normalized = str(value).casefold()
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def build_normalized_lookup(rows, attribute: str):
    lookup = {}

    for row in rows:
        value = getattr(row, attribute)
        if value is None:
            continue

        key = normalize_compare_text(value)
        if key in lookup:
            lookup[key] = None
            continue

        lookup[key] = row

    return lookup


def build_keyword_split_signature(value) -> tuple[str, ...]:
    """키워드 문자열을 분해해 비교용 시그니처를 만든다.

    예: "Action, Adventure" == "adventure / action"
    """
    normalized = normalize_compare_text(value)
    if not normalized:
        return tuple()

    # 쉼표/슬래시/&/|/+/세미콜론/불릿 등을 구분자로 취급
    # and는 독립 토큰일 때만 구분자로 취급
    normalized = re.sub(r"\band\b", ",", normalized)
    parts = re.split(r"\s*[,/&|;+·]\s*", normalized)

    tokens = []
    for part in parts:
        token = normalize_compare_text(part)
        if token:
            tokens.append(token)

    # 순서 차이를 제거하고, 중복 토큰은 1개로 축약
    return tuple(sorted(set(tokens)))


def build_keyword_signature_lookup(rows, attribute: str):
    lookup = {}

    for row in rows:
        value = getattr(row, attribute)
        signature = build_keyword_split_signature(value)
        if not signature:
            continue

        if signature in lookup:
            lookup[signature] = None
            continue

        lookup[signature] = row

    return lookup