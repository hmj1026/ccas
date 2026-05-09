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
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="bill")
```

## Alembic Migrations

- After **any** model change: `uv run alembic revision --autogenerate -m "<description>"`
- Apply migrations: `uv run alembic upgrade head`
- Never edit generated migration files to add business logic
- Migration descriptions use kebab-case: `add-bill-status-column`
