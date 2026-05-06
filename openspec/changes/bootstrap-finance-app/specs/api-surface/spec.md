## ADDED Requirements

### Requirement: Single operation registry
The system SHALL maintain one operation registry in `core.operations` where each operation is a Python callable accompanied by a Pydantic input model and a Pydantic output model. Both the REST API and the MCP server SHALL expose every registered operation by walking this registry — neither SHALL define operations independently.

#### Scenario: New operation appears on both surfaces
- **WHEN** a new operation `delete_category` is added to the registry with input/output models
- **THEN** it is available as a REST route AND as an MCP tool with no additional code in `api/` or `mcp/`

#### Scenario: REST and MCP schemas match the registry
- **FOR EACH** operation in the registry
- **THEN** the REST route's request/response schema and the MCP tool's input/output schema both derive from the same Pydantic models

### Requirement: REST API transport
The system SHALL expose the operation registry as a JSON REST API served by FastAPI. Endpoints SHALL accept and return JSON, validate inputs against the registered Pydantic input model, and return outputs serialized via the registered output model. Responses SHALL use standard HTTP status codes (`200` success, `400` validation, `401` auth, `404` not found, `409` conflict, `500` server error).

#### Scenario: Validation failure returns 400 with field detail
- **WHEN** a request supplies a field of the wrong type
- **THEN** the response status is `400` and the body contains a list of field errors naming each invalid field

#### Scenario: Conflict returns 409
- **WHEN** an operation fails because of a uniqueness/duplicate constraint (e.g., duplicate account name, duplicate-content draft confirmation)
- **THEN** the response status is `409` with a message identifying the conflicting entity

### Requirement: API key authentication
All REST endpoints (except a `GET /health` liveness probe) SHALL require an `Authorization: Bearer <api-key>` header. The expected key SHALL be loaded from configuration. Requests with a missing or wrong key SHALL return `401`. The system MUST NOT log the raw API key.

#### Scenario: Missing key
- **WHEN** a request to a protected endpoint omits the `Authorization` header
- **THEN** the response is `401` with body `{"error": "missing api key"}`

#### Scenario: Wrong key
- **WHEN** a request supplies an `Authorization: Bearer <wrong>` header
- **THEN** the response is `401` and the wrong key value does not appear in any log line

#### Scenario: Health endpoint is unauthenticated
- **WHEN** an unauthenticated `GET /health` is made
- **THEN** the response is `200` with body `{"status": "ok"}`

### Requirement: MCP server transport
The system SHALL expose the operation registry as an MCP server using the official MCP Python SDK. Each registered operation SHALL be advertised as an MCP tool whose JSON Schema is derived from the operation's Pydantic input model and whose return is the operation's Pydantic output model serialized to JSON.

#### Scenario: Tools listing reflects registry
- **WHEN** an MCP client lists tools
- **THEN** the response contains one tool per operation in the registry, each with name, description, and JSON Schema input

#### Scenario: Tool call invokes the same callable as REST
- **WHEN** an MCP client invokes a tool
- **THEN** the underlying Python callable is the same one a REST request would invoke, and the same authorization model applies

### Requirement: Shared authorization between REST and MCP
The MCP server SHALL require the same API key as REST, supplied via MCP transport-appropriate auth (e.g., header on the MCP HTTP transport). Failed auth SHALL prevent tool listing and tool calls.

#### Scenario: MCP without key cannot list tools
- **WHEN** an MCP client connects without a valid API key
- **THEN** tool listing returns an authorization error and no tools are advertised

### Requirement: Operation contract test
The repository SHALL include an automated contract test that, for every operation in the registry, asserts both surfaces (REST and MCP) expose it with matching input and output schemas. The test SHALL fail if a new operation is added without appearing on both surfaces, or if the schemas diverge.

#### Scenario: Adding a registry operation makes the contract test pass on both surfaces
- **WHEN** a developer adds a new operation to the registry
- **THEN** the contract test discovers it and verifies it on both REST and MCP without additional test code

#### Scenario: Schema drift fails the test
- **WHEN** a developer hand-overrides the schema on one surface so it differs from the other
- **THEN** the contract test fails with an error that names the operation and the differing fields
