"""End-to-end example of the SKILL.md path. Run: python examples/agent_walkthrough.py

Simulates the first thing a careful agent should do before backtesting ChiNext stocks 2019-2026:
pre-flight coverage, acknowledge required context, query a few fills, stop correctly on a gap,
and emit a citation. No market data is used; prices are illustrative.
"""
import json
import marina_rules as mr

print("== 1-2. pre-flight ==")
# A natural first attempt: ask for everything under the board scope. This is *wrong* and Marina says so —
# statutory fees are not board-specific; they live under scope 'stock'. The gap is the signal.
naive = mr.coverage("XSHE", "chinext", ["price_limit_pct", "stamp_duty_sell"], "2019-01-01", "2026-10-19")
print("  naive (fees under 'chinext'):", naive["status"], "→ gaps:", [(g["rule"], g["from"], g["to"]) for g in naive["gaps"]])

# Correct: one coverage call per scope the simulation will actually select.
cov_px = mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19")
cov_fee = mr.coverage("XSHG+XSHE", "stock", ["stamp_duty_sell", "transfer_fee_each_side"], "2019-01-01", "2026-10-19")
for name, cov in (("price limits / chinext", cov_px), ("fees / stock", cov_fee)):
    print(f"  {name}: {cov['status']}  verification={cov['verification']}  records={len(cov['records'])}")
    assert cov["status"] == "complete", cov
print(json.dumps({k: cov_px[k] for k in ("required_context", "excludes")}, ensure_ascii=False))
cov = cov_px

print("\n== 3. context the caller must hold per security/day ==")
print("  ", cov["required_context"], "→ without point-in-time st_status you may NOT select 'chinext' for a stock that might be ST")

print("\n== 4. per-fill queries ==")
for date, pc in [("2020-08-21", 10.00), ("2020-08-24", 10.00), ("2026-07-06", 10.00)]:
    up, dn = mr.limit_price(pc, "chinext", date, "XSHE")
    print(f"  {date}  prev_close {pc:.2f} → limit up {up:.2f} / down {dn:.2f}   stamp {mr.rule_at('stamp_duty_sell', date)}")

print("\n== 6. stopping correctly ==")
bad = mr.coverage("XSHG+XSHE", "stock", ["stamp_duty_sell"], "2004-01-01", "2010-01-01")
print("  window 2004-2010:", bad["status"], "gaps:", bad["gaps"])
try:
    mr.rule_at("stamp_duty_sell", "2005-01-01")
except KeyError as e:
    print("  rule_at →", type(e).__name__, "—", e, "(correct: no fallback)")
unsup = mr.coverage("XSHG", "lof_gold", ["price_limit_pct"], "2024-01-01", "2025-01-01")
print("  scope lof_gold:", unsup["status"], "scope_known:", unsup["scope_known"], "(not a scope Marina knows)")

print("\n== 5. citation to embed in the result ==")
print("  ", mr.citation(short=False))
