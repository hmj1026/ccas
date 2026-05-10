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
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)  # minor units (cents)
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="bill")
```

## Money Representation

- **All monetary fields are `Integer` minor units (cents) — never `Float`/`Numeric`**. Naming convention: `amount_minor_units` for new fields; legacy `amount` columns are also int-cents.
- Parsers multiply by 100 on ingestion; API layer divides by 100 (or formats directly) before responding.
- Avoid floating-point math anywhere in the parse → store → API path.

## Alembic Migrations

- After **any** model change: `uv run alembic revision --autogenerate -m "<description>"`
- Apply migrations: `uv run alembic upgrade head`
- Never edit generated migration files to add business logic
- Migration descriptions use kebab-case: `add-bill-status-column`
