"""What goes wrong when a backtest hard-codes today's rules — six fills, each where the rule was different.

    python examples/hardcoded_vs_marina.py

This is arithmetic on single fills, not a backtest: for each case it prints the number a backtest gets when it uses
the rule in force today, and the number Marina gives for that trade date, with the record it comes from. The cases
are illustrations chosen at rule changes; they say nothing about how often such fills occur in a strategy.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import marina_rules as mr  # noqa: E402

TODAY = "2026-11-13"


def cases() -> list:
    out = []

    def limit(label, prev_close, scope_then, date, market, scope_today=None):
        hard = mr.limit_price(prev_close, scope_today or scope_then, TODAY, market)
        real = mr.limit_price(prev_close, scope_then, date, market)
        rec = mr.record_at("price_limit_pct", date, scope_then, market)
        out.append({"case": label, "date": date, "quantity": f"limit-up / limit-down, previous close {prev_close}",
                    "hard_coded_today": hard, "marina": real, "record": rec.id})

    def fee(label, turnover, date, market):
        hard = mr.statutory_fee_floor(turnover, "sell", TODAY, market)
        real = mr.statutory_fee_floor(turnover, "sell", date, market)
        rec = mr.record_at("stamp_duty_sell", date, "stock", market)
        out.append({"case": label, "date": date, "quantity": f"stamp duty + transfer fee, sell {turnover:,.0f}",
                    "hard_coded_today": round(hard, 2), "marina": round(real, 2), "record": rec.id})

    limit("ChiNext before the 2020-08-24 reform (band was 10%, is 20%)", 10.00, "chinext", "2020-08-21", "XSHE")
    limit("ST stock treated as an ordinary main-board stock (5%, not 10%)", 10.00, "st_main", "2024-06-14", "XSHE",
          scope_today="main_board")
    limit("IPO in its first five days treated as an ordinary stock (no limit)", 10.00, "ipo_first5_main", "2024-01-30",
          "XSHG+XSHE", scope_today="main_board")
    limit("Convertible bond treated as a stock (band 20% on a 0.001 tick, not 10% on 0.01)", 100.003, "convertible", "2023-01-04", "XSHE",
          scope_today="main_board")
    fee("Sell in April 2008 (stamp duty 0.3%, today 0.05%)", 100000, "2008-04-23", "XSHE")
    fee("Sell just before the 2023-08-28 cut (stamp duty 0.1%, today 0.05%)", 100000, "2023-08-25", "XSHE")
    return out


def main() -> int:
    print(mr.citation())
    for c in cases():
        print(f"\n{c['case']}\n  {c['date']}: {c['quantity']}\n"
              f"    hard-coded (rules of {TODAY}): {c['hard_coded_today']}\n"
              f"    Marina (rules of that day):      {c['marina']}   ← {c['record']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
