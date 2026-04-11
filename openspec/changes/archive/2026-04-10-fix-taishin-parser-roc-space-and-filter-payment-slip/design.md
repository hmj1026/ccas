# Design: TAISHIN Parser Fix + PaymentSlip Filter

## Context

TAISHIN 真實 PDF 使用 ROC 民國年，並在「繳款截止日」與日期之間使用空白而非冒號：
```
帳 務 資 訊
帳單結帳日 113/11/12
繳款截止日 113/11/27
```
另外每期有兩份附件：信用卡電子帳單 `TSB_Creditcard_Estatement_YYYYMM.pdf` 與繳款聯 `TSB_PaymentSlip_YYYYMM.pdf`；只有前者是帳單，後者需過濾。

## Decisions

### D1: 冒號可選 regex

以最小侵入改動為主，只把 `[：:]` 改為 `[：:]?\s*`。保持現有結構。

### D2: PaymentSlip 放進 `ingestor/filters.py` 共用黑名單

延續 SINOPAC `繳款聯` 的解法，以 `dict[str, tuple[str, ...]]` 形式集中管理。`TAISHIN -> ("PaymentSlip",)`。
