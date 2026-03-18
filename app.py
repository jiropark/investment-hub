"""Investment Hub - 3개 투자 전략 통합 대시보드"""

import json
import os
import urllib.request
from datetime import datetime
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# 각 서비스 URL (NAS Docker 내부에서 host.docker.internal 사용)
HOST = os.getenv("SERVICE_HOST", "host.docker.internal")
SERVICES = {
    "kis": {
        "name": "KIS 눌림목 스켈핑",
        "port": int(os.getenv("KIS_PORT", "8089")),
        "color": "#4dabf7",
        "icon": "📊",
        "strategy": "눌림목 자동매매 (pullback)",
        "desc": "KIS 모의투자 API, 상승률+거래량 스크리닝, 5% 익절/손절",
    },
    "stock": {
        "name": "AI 뉴스 감성분석",
        "port": int(os.getenv("STOCK_PORT", "8088")),
        "color": "#51cf66",
        "icon": "🤖",
        "strategy": "뉴스 감성분석 + 점수 기반 매매",
        "desc": "Claude Haiku 감성분석, 멀티소스 뉴스, 자기학습 가중치",
    },
    "kospi": {
        "name": "KOSPI100 RLM 모멘텀",
        "port": int(os.getenv("KOSPI_PORT", "8090")),
        "color": "#ffd43b",
        "icon": "📈",
        "strategy": "Robust Lazy Momentum (월간 리밸런싱)",
        "desc": "KOSPI100 모멘텀 스코어링, MA120 필터, 10% 트레일링스탑",
    },
    "vtp": {
        "name": "VTP 거래량·종가 돌파",
        "port": int(os.getenv("VTP_PORT", "8092")),
        "color": "#e599f7",
        "icon": "🎯",
        "strategy": "거래량 이상 + 목표종가 돌파 (스코어링)",
        "desc": "거래량·가격 스코어링 0-100, ATR 기반 갭 진입, 3중 손절",
    },
}


def fetch_json(port, path, timeout=5):
    """서비스 API에서 JSON 가져오기"""
    url = f"http://{HOST}:{port}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def fetch_all():
    """4개 서비스에서 포트폴리오 데이터 수집"""
    results = {}
    for key, svc in SERVICES.items():
        port = svc["port"]
        portfolio = fetch_json(port, "/api/portfolio")

        trades = []
        if key == "kis":
            trades_raw = fetch_json(port, "/api/trades")
            if isinstance(trades_raw, list):
                trades = trades_raw[:5]
        elif key == "stock":
            trades_raw = fetch_json(port, "/api/trades")
            if isinstance(trades_raw, list):
                trades = trades_raw[:5]
        elif key == "kospi":
            trades_raw = fetch_json(port, "/api/trades?limit=5")
            if isinstance(trades_raw, list):
                trades = trades_raw[:5]
            elif isinstance(trades_raw, dict) and "trades" in trades_raw:
                trades = trades_raw["trades"][:5]

        extra = {}
        if key == "kis":
            signals = fetch_json(port, "/api/signals")
            if isinstance(signals, list):
                extra["signal_count"] = len(signals)
                extra["buy_signals"] = sum(1 for s in signals if s.get("signal_type") == "BUY")
        elif key == "stock":
            scores = fetch_json(port, "/api/scores")
            if isinstance(scores, list):
                extra["top_scores"] = scores[:5]
            learning = fetch_json(port, "/api/learning")
            if isinstance(learning, dict) and "error" not in learning:
                extra["learning"] = learning
        elif key == "kospi":
            market = fetch_json(port, "/api/market")
            if isinstance(market, list) and market:
                extra["market"] = market[-1] if market else {}
            elif isinstance(market, dict):
                extra["market"] = market
        elif key == "vtp":
            signals = fetch_json(port, "/api/signals")
            if isinstance(signals, list):
                extra["signal_count"] = len(signals)
                extra["top_signals"] = signals[:3]

        results[key] = {
            "info": svc,
            "portfolio": portfolio,
            "trades": trades,
            "extra": extra,
            "online": "error" not in portfolio,
        }

    return results


def safe_get(d, *keys, default=0):
    """중첩 딕셔너리에서 안전하게 값 추출"""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


@app.route("/")
def index():
    data = fetch_all()

    # 합산 계산
    total_asset = 0
    total_initial = 0
    online_count = 0

    for key, item in data.items():
        if item["online"]:
            online_count += 1
            p = item["portfolio"]
            total_asset += p.get("total_asset", 0) or p.get("total_value", 0) or 0
            total_initial += p.get("initial_capital", 5_000_000) or 5_000_000

    total_return = ((total_asset / total_initial - 1) * 100) if total_initial > 0 else 0

    return render_template(
        "index.html",
        data=data,
        total_asset=total_asset,
        total_initial=total_initial,
        total_return=total_return,
        online_count=online_count,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        safe_get=safe_get,
    )


@app.route("/api/summary")
def api_summary():
    """JSON API for external consumption"""
    data = fetch_all()
    summary = {}
    for key, item in data.items():
        summary[key] = {
            "name": item["info"]["name"],
            "online": item["online"],
            "portfolio": item["portfolio"] if item["online"] else None,
        }
    return jsonify(summary)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8091"))
    app.run(host="0.0.0.0", port=port, debug=False)
