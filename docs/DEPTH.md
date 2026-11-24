# 深度登记 中转行李清分台

中转主管逐牌核对航段窗口与动作末态。跨日同航班号不能替代航段实例。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 扫描原件采信 | 查看射频重报和隔离行 | `/desk/scans` `/api/stage/scans` | `app/modules/scans/service.py` | `tests/test_scans.py` |
| M2 航段候选关联 | 核对候选段和提示 | `/desk/legs` `/api/stage/legs` | `app/modules/legs/service.py` | `tests/test_legs.py` |
| M3 扫件有序回放 | 按生效时刻核对动作 | `/desk/replay` `/api/stage/replay` | `app/modules/replay/service.py` | `tests/test_replay.py` |
| M4 错载与漏扫归因 | 按牌追踪待证与错装 | `/desk/exceptions` `/api/stage/exceptions` | `app/modules/exceptions/service.py` | `tests/test_exceptions.py` |
| M5 行李去向对账 | 勾稽计划段与去向件数 | `/` `/api/stage/ledger` | `app/modules/ledger/service.py` | `tests/test_ledger.py` |
| M6 批次留档复跑 | 保存并复算原件 | `/desk/archive` `POST /api/archive` | `app/modules/archive/service.py` `app/modules/archive/store.py` | `tests/test_archive.py` |
| M7 联程证据签发 | 验摘要并下载联程证据 | `/desk/evidence` `/api/evidence/<run>/export` | `app/modules/evidence/bundle.py` | `tests/test_evidence.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | 脏扫描首列 BOM | 扫描号丢失 | 解码时去首 BOM | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bom` |
| TRAP-04 | 脏扫描第 16 行重复表头 | 误计为扫描 | 计独立分段 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_sections` |
| TRAP-05 | E17 多余分隔列 | 宽度误收 | 原行隔离 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bad_width` |
| TRAP-07 | E18 时间 N/A | 默认零时 | 空值隔离 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_sentinel` |
| TRAP-08 | 清单 000101 | 强转丢零 | 字符串关联 | `app/modules/legs/contracts.py` | `tests/test_legs.py::test_tag_preserved` |
| TRAP-11 | E03 特殊偏移重复 | 误认成不同事件 | UTC 后比较 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_equivalent_offset_duplicate` |
| TRAP-13 | E02 迟到撤下 | 收件顺序末态错误 | 标迟到后按生效回放 | `app/modules/replay/radio.py` | `tests/test_replay.py::test_late_offload_before_reload` |
| TRAP-14 | E12 同键相反动作 | 后写覆盖 | 全组隔离 | `app/modules/scans/service.py` | `tests/test_scans.py::test_conflicting_id` |
| TRAP-23 | E04 恰逢跨日换窗 | 同时匹配两段 | 左闭右开 | `app/modules/legs/service.py` | `tests/test_legs.py::test_boundary_handoff` |
| TRAP-31 | 停飞后晚到撤下落入续飞窗口 | 误归续飞段或窗外漏撤 | 凭原航段装机凭据回放，标 `OUTSIDE_REPLAY`，续飞装机仍按窗归属 | `app/modules/legs/service.py` | `tests/test_handover.py::test_late_offload_replays_to_original_leg_during_continuation_window` |
| TRAP-32 | 清单外已装件未撤即交接 | 舱里有人也放行 | 逐航段清舱结论，清单外未撤与待证一并阻断 | `app/modules/ledger/handover.py` | `tests/test_handover.py::test_handover_blocked_by_unlisted_loaded_bag` |

## 清舱交接

每个航段给出 `可交接 / 不可交接`。阻断条件：该段清单件仍有 `pending` 待证，或清单外行李在该段末态仍为 `LOADED`（一件未撤即不可交接）。错装件按实际所在航段核算，不阻断原航段。归档结论随原件摘要固化，重跑走唯一键复用，不覆盖原结论。

## 对账规则

脏样例清单 12 = 3 已装 + 8 待证 + 1 明确未装，错装 2 件另列。扫描原件记录 24 = 17 采信 + 4 隔离 + 1 重报 + 1 重复表头 + 1 空行。

## 已知范围

文件内容通过限长 JSON 提交。样例为机场单站观测，时间窗由机场清单提供。扫描尾播放已采信记录的收件流。
