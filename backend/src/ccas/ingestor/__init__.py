"""Gmail 帳單匯入模組。

提供 run_ingestion_job() 作為單次 Gmail ingestion batch 入口，
供排程模組（scheduler）或手動觸發呼叫。
"""

from ccas.ingestor.job import IngestionSummary, run_ingestion_job

__all__ = ["IngestionSummary", "run_ingestion_job"]
