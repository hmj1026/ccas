"""Bank parser 實作目錄。

命名慣例：每個銀行以 bank_code 小寫為模組名，
版本化 parser 檔案以 ``{bank_code}_v{N}.py`` 命名。

範例結構::

    banks/
    ├── __init__.py
    ├── ctbc_v1.py      # 中國信託 v1 parser
    ├── ctbc_v2.py      # 中國信託 v2 parser
    ├── cathay_v1.py    # 國泰 v1 parser
    └── esun_v1.py      # 玉山 v1 parser

每個 parser 模組須定義一個繼承 BankParser 的類別，
並設定 bank_code 與 version 屬性。
"""

from . import cathay_v1, ctbc_v1, esun_v1, fubon_v1, sinopac_v1, taishin_v1, ubot_v1

__all__ = [
    "cathay_v1",
    "ctbc_v1",
    "esun_v1",
    "fubon_v1",
    "sinopac_v1",
    "taishin_v1",
    "ubot_v1",
]
