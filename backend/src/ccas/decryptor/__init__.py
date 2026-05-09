"""PDF 解密模組。

提供批次 PDF 解密功能，將 staging 區的加密 PDF 以銀行密碼解密。
"""

from ccas.decryptor.job import DecryptionSummary, run_decryption_job

__all__ = ["DecryptionSummary", "run_decryption_job"]
