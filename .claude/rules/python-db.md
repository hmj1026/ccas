---
paths:
  - "**/models*.py"
  - "**/migrations/**/*.py"
  - "**/alembic/**/*.py"
---
# CCAS SQLAlchemy & Alembic Conventions

## SQLAlchemy Models

- Inherit from `Base` (DeclarativeBase)
- Always set `__tablename__`
- Use `Mapped[T]` with `mapped_column()` for all columns
- Relationships: `relationship()` with `back_populates`
- Constraints in `__table_args__` tuple

```python
class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # NTD whole dollars (元)
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="bill")
```

## Money Representation

- **全系統金額以 NTD 整數元儲存，不乘 100** — all monetary fields are `Integer` whole NTD dollars (元), never `Float`/`Numeric`. Naming convention: `amount_ntd` for new fields; legacy `amount` / `total_amount` columns are also integer NTD 元.
- Parsers emit integer NTD 元 and the pipeline persists them as-is; the API returns the same integers — **no unit conversion (×100 / ÷100) anywhere**.
- Avoid floating-point math anywhere in the parse → store → API path.

## Alembic Migrations

- After **any** model change: `uv run alembic revision --autogenerate -m "<description>"`
- Apply migrations: `uv run alembic upgrade head`
- Never edit generated migration files to add business logic
- Migration descriptions use kebab-case: `add-bill-status-column`
