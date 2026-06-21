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

模組載入採「動態探索」：凡符合命名慣例 ``{bank_code}_v{N}``（regex
``^[a-z]+_v\\d+$``）的子模組都會被自動 import，觸發各模組底部的
``registry.register()`` 副作用。新增 parser 只需放入符合命名的檔案，
無須再手動維護此處的 import 清單。非 parser 的輔助子套件（如 ``ctbc/``）
因不符命名而被排除。
"""

import importlib
import pkgutil
import re

_PARSER_MODULE_RE = re.compile(r"^[a-z]+_v\d+$")


def _discover_parser_modules() -> tuple[str, ...]:
    """探索並 import 所有符合命名慣例的 parser 子模組，回傳其名稱（已排序）。"""
    discovered: list[str] = []
    for module_info in pkgutil.iter_modules(__path__):
        if _PARSER_MODULE_RE.match(module_info.name):
            importlib.import_module(f"{__name__}.{module_info.name}")
            discovered.append(module_info.name)
    return tuple(sorted(discovered))


# 模組 import 時即執行探索（副作用：各 parser 模組註冊進 registry）。
# 公開為常數供測試斷言「無漏載」。
DISCOVERED_PARSER_MODULES: tuple[str, ...] = _discover_parser_modules()
