# Marina：交易制度历史数据（交易规则数据集）

**把各市场的交易制度做成按时间点可查的数据：涨跌停幅度、印花税和过户费、交易时段、最小报价单位、T+N 交收——每条规则从哪天起生效、依据哪份官方文件，都有记录。给回测引擎和 AI Agent 用。**

A 股回测里最常见的一类错误不是策略写错，而是交易规则用错：把创业板涨跌幅写死成 20%（2020-08-24 之前是 10%），忘了 ST 股是 5%，用今天的印花税率算十年前的成交，或者用 `round()` 算涨跌停价（交易所是四舍五入，`round()` 不是）。Marina 把这些规则连同生效日期和出处放进一张公开的表里，查询时按交易日返回当天实际有效的规则；查不到就报错，不猜。

完整说明、各市场的记录数和覆盖范围以英文版为准：[README.md](README.md)。本页是中文入门。

## 安装和查询

```bash
pip install marina-rules           # 代码包；数据包 marina-rules-data 作为依赖一起装上，运行时不联网
pip install -U marina-rules-data   # 以后只升级数据：规则更新，代码不动
```

Marina 分成两个包，做法和时区数据库一样：**`marina-rules-data`** 是规则数据，按日期编版本（`YYYY.MM.DD`），数据有变化就发；**`marina-rules`** 是读数据的代码，按语义化版本编号，只在功能变化时发。两者可以分别升级；代码在导入时会检查装着的数据能不能读，读不了就直接报错并说明该升级哪个包。

```python
import marina_rules as mr

mr.rule_at("stamp_duty_sell", "2023-08-25")                      # 0.001   印花税减半之前
mr.rule_at("stamp_duty_sell", "2023-08-28")                      # 0.0005  减半当日起
mr.rule_at("price_limit_pct", "2020-08-21", "chinext", "XSHE")   # 0.1     创业板注册制改革前
mr.rule_at("price_limit_pct", "2020-08-24", "chinext", "XSHE")   # 0.2     改革当日起
mr.limit_price(10.00, "chinext", "2021-03-01", "XSHE")           # (12.0, 8.0)  按交易所的取整规则算出的涨跌停价
mr.limit_price(10.00, "ipo_first5_main", "2024-01-30", "XSHG+XSHE")   # None  新股上市前五日不设涨跌幅
mr.rule_at("stamp_duty_sell", "2005-01-01")                      # KeyError  没有记录就报错，从不给默认值
mr.statutory_fee_floor(86420.00, "sell", "2023-08-28", "XSHG")   # 44.0742  一笔卖出的印花税 + 过户费
mr.citation()   # 'rules: marina-rules-data@<数据版本> sha256:<16 位摘要> code: marina-rules@<代码版本>'
```

三点约定：

- **日期写成 `YYYY-MM-DD`**，或者传 `date` / `datetime` 对象。`20230828`、`2023/8/28`、整数都会报 `ValueError` 并提示正确写法——规则区间按 ISO 文本比较，别的写法会选错时期，所以拒绝而不是猜。数据商常见的 `YYYYMMDD` 请先转换：`f"{s[:4]}-{s[4:6]}-{s[6:]}"`。
- **市场用 ISO 10383 代码**：上交所 `XSHG`、深交所 `XSHE`、北交所 `BJSE`、港交所 `XHKG`、纽交所 `XNYS`、纳斯达克 `XNAS`、中金所 `CCFX`、上期所 `XSGE`、上期能源 `XINE`、郑商所 `XZCE`、广期所 `GFEX`。写 `SZSE`、`SSE` 会被拒绝，报错里会列出正确的代码。
- **一只股票属于哪个范围（scope）由你提供**。主板、创业板、科创板、北交所、ST、新股上市前五日、退市整理期各是不同的 scope。Marina 只存规则，不存某只股票哪天是 ST、哪天上市；它不会替你推断。

## 先问有什么，再问值是多少

规则只按它登记的名字回答。名字不要猜，先查：

```python
mr.scopes()                         # 全部 scope：说明，以及各自需要你提供的上下文（"hk" / "us" 查港股、美股）
mr.rules_for("chinext", "XSHE")     # 这个 scope 有哪些规则，各自的生效区间
```

```bash
marina-rules scopes
marina-rules rules chinext XSHE
marina-rules query price_limit_pct 2024-06-14 st_main XSHE --context board=main_board,st_status=true
marina-rules fees 86420 sell 2023-08-28 XSHG
```

查不到时，报错信息会说明这个 scope 实际有哪些规则、哪些名字相近、这条规则有哪些区间。相近的名字是另一条规则（股票的 `price_limit_pct` 以前收盘价为基准，期货是 `price_limit_pct_of_prev_settlement`，以前结算价为基准），先看定义再用。

## 回测前先预检整个区间

```python
mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19")
# {'status': 'complete', 'gaps': [], 'required_context': ['board', 'st_status', 'listing_day_index'], ...}
```

`coverage()` 回答「这段时间、这个 scope、这些规则，Marina 是否每一天都答得上」：`complete`、`partial`（附具体缺口）或 `unsupported`。已知答不上的地方列在各市场的 `known_gaps.yaml` 里，每条都有原因，所以「不支持」可以被引用，而不是被悄悄绕过去。

## 给 Agent 和其他语言：统一的判定结果

```python
from marina_rules.contract import resolve
resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE", {"board": "main_board", "st_status": True})
# {'status': 'DETERMINED', 'result': {'value': 0.05, ...}, 'record_id': 'cn.limit.st_main.1998-04-22', ...}
```

`resolve()` 不抛数据类异常，只返回一个带 `status` 的字典：`DETERMINED`（有答案）、`MISSING_CONTEXT`（缺你该提供的上下文）、`OUT_OF_COVERAGE`（没有覆盖，附 `alternatives` 说明有什么）等。只有 `DETERMINED` 才有值；其他状态一律停下来，不要自己补一个数。给 Agent 的使用说明在 [SKILL.md](SKILL.md)，安装后可用 `marina-rules skill` 或 `mr.skill_text()` 读到；能问什么由 `marina-rules capabilities` 列出。

数据本身是 [`data/`](data/) 下的 YAML 文件，不装 Python 包也能用任何语言读。

## 检查一份成交记录

```bash
python -m marina_rules.check fills.csv
```

逐笔核对回测或实盘的成交：买入价不高于涨停价、卖出价不低于跌停价、价格落在当日有效的最小报价单位上、费用不低于法定下限。目前只检查 A 股成交。`prev_close` 必须和成交价同一口径（都不复权；除权除息日用交易所公布的除权参考价）。全部选项和各类发现的含义见英文版的 [Check a fill log](README.md#check-a-fill-log)。

回测引擎自己导出的成交记录不用手工改格式，直接读：

```bash
marina-check trades.csv --format rqalpha --bars daily.csv --bars-format tushare \
             --listing stock_basic.csv --listing-format tushare --st stock_st.csv --st-format tushare
marina-rules adapt --list-formats      # 全部格式、各自读哪些列、依据是什么
```

`--format` 支持 RQAlpha、vn.py、backtrader、掘金，以及按常见列名识别的通用表格（`generic`，列名不同时用 `--map 字段=列名` 指明）。成交记录里没有的前收盘价、ST 状态、上市日期，从行情数据源的表里补：`--bars`（Tushare `daily`、baostock、RQData 的日线）、`--st`、`--listing`。日线必须是不复权的；前收盘价只取数据源明确标为「前收盘」的那一列，不会用别的列推算。没有 ST 信息时这些行会报「范围无法确定」，加 `--assume-not-st` 可以按非 ST 检查，但那是放宽模式，不给验证印章。聚宽、米筐平台、PTrade、QMT 的导出格式没能从一手资料查实，暂时没有专门的格式，用 `generic` 加 `--map`。

## 覆盖范围

| 市场 | 记录的规则 | 起始 |
|---|---|---|
| A 股（上交所、深交所、北交所） | 涨跌幅限制（含 ST、新股、退市整理期、B 股、ETF、可转债、REITs）、印花税、过户费、佣金上限与最低佣金、交易时段与集合竞价、最小报价单位、最短持有期（T+1 / T+0） | 2006-07-01 |
| 中金所股指期货（IF、IH、IC、IM） | 涨跌停板、手续费、保证金、交易时段 | 各品种上市日（IF 为 2010-04-16） |
| 中金所国债期货（TF、T、TS、TL） | 同上 | 各品种上市日（TF 为 2013-09-06） |
| 上期所、上期能源、郑商所、广期所商品期货 | 保证金、涨跌停板、手续费（含平今）、日内回转 | 2024-01-01 |
| 港股（股票、ETF） | 收市竞价与开市前时段价格限制、市调机制、印花税与交易费用、交易时段、价位表、T+2 交收、沽空价格规则 | 2010 |
| 美股（股票、ETF） | LULD 涨跌幅区间、全市场熔断、SEC 与 FINRA 费用、交易时段、最小报价单位、交收周期（T+3 → T+2 → T+1）、沽空价格测试 | 2010 |
| 大商所、加密货币 | 未覆盖 | — |

各市场的成熟度不同：A 股、中金所、上期所、上期能源的记录多数是 `verified`，郑商所、广期所、港股、美股多数是 `single-source`，属于初步覆盖。每个市场的记录数、已知缺口和「核对到哪一天」见英文版的 [Coverage](README.md#coverage)。空着的格子是有意空着：缺的规则会报 `KeyError`，不会返回一个猜测值。

## 每条记录可信到什么程度

每条记录都带验证级别，写在数据里：

| 级别 | 含义 |
|---|---|
| `verified` | 至少一个官方一手来源（交易所、部委、登记结算机构）写明了这个值和日期，或至少两个独立的权威来源一致。每个来源都附原文引文和所抓取文件的内容哈希 |
| `single-source` | 只有一个来源，或官方来源里的日期或数值需要推断 |
| `unverified` | 只有二手来源，或来源之间有分歧（分歧记在 `notes` 里） |

API 里传 `strict=True` 会拒绝 `unverified` 的记录。

## 引用和复现

把 `mr.citation()` 的输出写进你发布的每一份结果。这一行写明数据版本（`marina-rules-data@…`）、数据摘要（`sha256:…`，对规则文件本身计算）和读取它的代码版本（`code: marina-rules@…`）：带着它，任何人都能用字节完全相同的规则重跑；不带它，结果无法复现。命令行 `marina-rules version` 输出同一行。

该用哪个版本，看用途（详见英文版的 [Which version to use](README.md#which-version-to-use)）：

- **要发表的研究**：固定数据版本（`pip install marina-rules "marina-rules-data==<数据版本>"`），把 `mr.citation()` 写进结果。
- **每天都在跑的东西**（模拟盘或实盘 Agent、每晚的回测）：每周升级数据包（`pip install -U marina-rules-data`），并打开 `require_tracked=True`，超过维护者核对日期的查询会被拒绝，而不是沿用最后一条已知规则。
- **每次升级数据之后**：用 `python -m marina_rules.diff <旧数据目录> <新数据目录>` 查看哪些规则变了、哪些回测需要重跑，做法见英文版的 [Upgrading](README.md#upgrading-diff_rules)。

## Marina 不包含什么

只收「影响订单能否成交、以什么价格成交、成本多少」的规则。成分股名单、ST 名单、停牌名单、行情、复权因子都不收——那些是数据，有归属和授权问题；Marina 只存规则。它也不是权威解释，规则本身以交易所公告为准。

## 许可

数据（`data/`、`docs/`，即 `marina-rules-data` 包）：[CC0 1.0](LICENSE-DATA)，不保留任何权利。代码（`src/`、`scripts/`、`tests/`，即 `marina-rules` 包）：[MIT](LICENSE)。

欢迎补充和纠错：每个合并请求一条记录，附一手来源链接。见 [CONTRIBUTING.md](CONTRIBUTING.md)。
