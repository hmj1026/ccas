---
paths:
  - "**/routers/**/*.py"
  - "**/api/**/*.py"
  - "**/schemas/**/*.py"
---
# CCAS FastAPI & API Conventions

## API Response Format

All endpoints use the unified envelope:

- Success: `ApiResponse[T](data=result)` -> `{"success": true, "data": T, "message": ""}`
- Paginated: `PaginatedResponse[T]` -> adds `pagination` field
- Error: `{"success": false, "message": "reason", "data": null}`
- Always set `response_model=ApiResponse[T]` or `PaginatedResponse[T]`

## FastAPI Patterns

- Auth: `Depends(verify_token)` applied globally via router dependencies
- DB: `Depends(get_db_session)` yields async session
- Query params: annotate with `Query()` including validators
- CORS: configured in `create_app()` app factory

```python
@router.get("/bills", response_model=PaginatedResponse[BillSchema])
async def list_bills(
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db_session),
    _: str = Depends(verify_token),
) -> PaginatedResponse[BillSchema]:
    ...
```

## Schemas

- Request/response schemas in `ccas/schemas/`
- Use Pydantic v2 `model_config = ConfigDict(from_attributes=True)` for ORM models
- Never return SQLAlchemy model instances directly from endpoints
