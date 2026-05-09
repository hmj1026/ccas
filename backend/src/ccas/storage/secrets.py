"""Master key 管理與 Fernet 對稱加密。

本模組提供 ``MasterKeyManager``，封裝 ``${CCAS_DATA_LOCATION}/secrets/master.key``
的 lazy 讀取、首次自動產生（權限 0600），以及 Fernet encrypt / decrypt。

設計要點：
- ``load_or_create`` 為冪等：首次呼叫產生新 key，其後皆讀既有檔。
- 寫檔用 ``os.open(..., O_WRONLY | O_CREAT | O_EXCL, 0o600)`` 避免 race，
  並在既有 dir 缺少時自動建立。
- ``decrypt`` 在 master.key 不匹配時 raise ``MasterKeyMismatchError``，
  訊息明示「請確認 ${CCAS_DATA_LOCATION} 完整還原」，便於 operator 排查
  備份遺失情況（spec oauth-onboarding-ui §1.1 要求 fail-loud）。

不依賴 ``Settings``（只吃 ``Path``），便於單元測試與 entrypoint 端的呼叫者解耦。
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from ccas.errors import CcasError

logger = logging.getLogger(__name__)


class MasterKeyMismatchError(CcasError):
    """master.key 與既有 ciphertext 不匹配。

    最常見成因：使用者只還原了 SQLite / staging，未還原 ``data/secrets/``，
    導致 entrypoint 自動產生新 master.key 但既有 ``bank_secrets`` 仍以舊 key
    加密。錯誤訊息會引導操作者還原備份。
    """


class MasterKeyManager:
    """封裝 master.key 檔的 lazy 讀寫與 Fernet 加密／解密。

    Attributes:
        master_key_path: master.key 檔路徑（通常為
            ``${CCAS_DATA_LOCATION}/secrets/master.key``）。
    """

    def __init__(self, master_key_path: Path) -> None:
        self.master_key_path = Path(master_key_path)
        self._fernet: Fernet | None = None
        # Guard the lazy ``_fernet`` cache against double-init when callers run
        # in a threadpool (e.g. FastAPI ``loop.run_in_executor``). The double-
        # checked locking pattern keeps the fast path lock-free.
        self._fernet_lock = threading.Lock()

    def load_or_create(self) -> bytes:
        """讀取既有 master.key；若不存在則產生新 key 並寫入 0600 檔。

        Returns:
            44-byte base64 url-safe encoded Fernet key。
        """
        if self.master_key_path.exists():
            return self.master_key_path.read_bytes()

        self.master_key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        # O_EXCL 確保若 race 已被別的 process 建立，第二者直接 fail，
        # 不會覆蓋已產生的 key（避免破壞既有加密資料）。
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(self.master_key_path, flags, 0o600)
        except FileExistsError:
            # 別的 process / call 在 exists() 與 open 之間搶先建立。
            return self.master_key_path.read_bytes()
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        # 在某些 umask 下 0o600 仍可能變成其他位元；明確再 chmod 一次。
        os.chmod(self.master_key_path, 0o600)
        logger.info(
            "已自動產生 master.key",
            extra={"path": str(self.master_key_path)},
        )
        return key

    def get_fernet(self) -> Fernet:
        """回傳已綁定 master key 的 Fernet instance（lazy + 快取，thread-safe）。"""
        if self._fernet is None:
            with self._fernet_lock:
                if self._fernet is None:
                    self._fernet = Fernet(self.load_or_create())
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """Fernet 加密；回傳 base64 url-safe ciphertext。"""
        token = self.get_fernet().encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Fernet 解密；不匹配時 raise MasterKeyMismatchError。

        Args:
            ciphertext: ``encrypt`` 產生的 base64 url-safe ciphertext。

        Raises:
            MasterKeyMismatchError: 當前 master.key 無法解密該 ciphertext，
                通常代表 ``data/secrets/master.key`` 與既有加密資料不同源。
        """
        try:
            plaintext = self.get_fernet().decrypt(ciphertext.encode("ascii"))
        except InvalidToken as exc:
            raise MasterKeyMismatchError(
                "master.key 與密文不匹配，請確認 ${CCAS_DATA_LOCATION} 完整備份還原",
                context={"key_path": str(self.master_key_path)},
            ) from exc
        return plaintext.decode("utf-8")
