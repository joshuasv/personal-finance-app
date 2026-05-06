# Extending the system

Adding a new bank, a new core operation, or a new chat surface should be
purely additive — you should not need to touch the existing core, API, MCP,
or CLI code.

## Add a new institution adapter

A new bank or PDF format is a single class plus one registration line.

1. **Implement the protocol** in a new module (`src/finance/ingestion/<bank>.py`):

   ```python
   from collections.abc import Iterable
   from pathlib import Path

   from finance.ingestion.protocols import InstitutionAdapter, ParsedTransaction

   class ChaseStatementAdapter:
       id = "chase-pdf"
       display_name = "Chase (PDF statement)"
       source_artifact_type = "application/pdf"

       def parse(self, path: Path) -> Iterable[ParsedTransaction]:
           # Yield one ParsedTransaction per statement line.
           # Sign convention: outflows negative, inflows positive.
           ...
   ```

2. **Register the adapter** in `src/finance/ingestion/__init__.py`:

   ```python
   from finance.ingestion.chase_pdf import ChaseStatementAdapter

   def build_default_adapter_registry() -> AdapterRegistry:
       registry = AdapterRegistry()
       registry.register_adapter(WiseStatementAdapter())
       registry.register_adapter(ChaseStatementAdapter())   # new
       return registry
   ```

3. **Add a fixture and a test** under `tests/fixtures/chase/` and
   `tests/unit/test_chase_adapter.py`. The integration tests in
   `tests/integration/test_ingestion.py` already cover all surfaces — they
   will pick up the new adapter automatically once it's registered.

The new adapter appears in `finance import --help`, on the Telegram inline
keyboard for PDF uploads, in the web UI's adapter picker, and in the
`list_adapters` operation. No surface code changes.

## Add a new core operation

Operations are how surfaces gain new capabilities. The shape:

1. **Define input and output Pydantic models** in
   `src/finance/core/operations/models.py`:

   ```python
   class TagTransactionIn(_BaseModel):
       transaction_id: int = Field(gt=0)
       tag: str = Field(min_length=1, max_length=60)

   class TagTransactionOut(_BaseModel):
       transaction: TransactionOut
   ```

2. **Implement the service** under `src/finance/core/services/` (or extend
   an existing one). Raise typed errors from `core.services.errors` for
   expected failure modes. The repository layer should stay thin — services
   carry the invariants.

3. **Wire the operation** in `src/finance/core/operations/bootstrap.py`:

   ```python
   def _tag_transaction(session, payload):
       tx = tag_transaction(session, transaction_id=payload.transaction_id, tag=payload.tag)
       return TagTransactionOut(transaction=TransactionOut.model_validate(tx))

   _OPERATIONS = (
       ...,
       Operation(
           name="tag_transaction",
           input_model=TagTransactionIn,
           output_model=TagTransactionOut,
           callable=_tag_transaction,
           description="Apply a free-form tag to a transaction.",
           tags=("ledger", "transactions"),
       ),
   )
   ```

The operation now appears as `POST /api/tag_transaction`, as an MCP tool
named `tag_transaction`, and is callable from the CLI by invoking the
operation directly. The contract test will fail your build if you forget to
register the operation on either REST or MCP, or if a hand-overridden
schema diverges from the Pydantic model.

## Add a new surface (e.g. a Slack bot, a watch folder, an LLM bridge)

A new surface is just another consumer of the operation registry. The rules
to keep the bootstrap-finance-app guarantees intact:

- **No business logic in the surface.** Surfaces parse input, build the
  operation's input model, call the registered callable, and render the
  output. Anything else belongs in `core/services` or as a new operation.
- **No direct DB access from the surface.** The surface receives a
  `session_maker` (or builds one from `Settings`) and lets each operation
  manage its own session via `_runtime.run_operation` or the equivalent.
- **Auth at the edge, not inside operations.** `api/auth.py` and
  `bots/telegram/auth.py` show the pattern: each surface implements its own
  trust boundary and dispatches to the registry only after the request is
  authorized.

For the LLM-bridge case specifically (the v2 backlog item): the surface
that wraps a personal AI assistant SHOULD drive operations through MCP
rather than reach into `core` directly. That preserves the constraint
that REST and MCP are the only programmatic surfaces — and it lets the
assistant's authorization re-use the existing API-key edge.
