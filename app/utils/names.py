from __future__ import annotations


KOREAN_COMPANY_NAMES = {
    "005490.KS": "POSCO홀딩스",
    "004020.KS": "현대제철",
    "010130.KS": "고려아연",
    "006260.KS": "LS",
    "051910.KS": "LG화학",
    "003670.KS": "포스코퓨처엠",
    "247540.KQ": "에코프로비엠",
    "267260.KS": "HD현대일렉트릭",
    "010120.KS": "LS ELECTRIC",
    "096770.KS": "SK이노베이션",
    "010950.KS": "S-Oil",
    "036460.KS": "한국가스공사",
    "015760.KS": "한국전력",
    "329180.KS": "HD현대중공업",
}


def display_company_name(ticker: str, company_name: str | None = None) -> str:
    return KOREAN_COMPANY_NAMES.get(ticker.upper(), company_name or ticker)
