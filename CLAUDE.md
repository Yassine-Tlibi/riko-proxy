# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Kiro Gateway** is a FastAPI-based proxy server that provides OpenAI-compatible and Anthropic-compatible APIs for Kiro (Amazon Q Developer / AWS CodeWhisperer). It acts as a transparent adapter, allowing tools built for OpenAI/Anthropic ecosystems to work with Claude models through the Kiro API.

- **Language**: Python 3.10+
- **Framework**: FastAPI with uvicorn ASGI server
- **License**: AGPL-3.0
- **Main Entry Point**: `main.py`
- **Core Package**: `kiro/` directory
- **Default Port**: 9000

## Core Philosophy

### Transparency First
- Preserve user's original intent and request structure
- Modifications only when necessary to work around Kiro API limitations or add opt-in enhancements
- Fix API quirks, not user decisions

### Systems Over Patches
- Build infrastructure that handles entire classes of issues, not one-off fixes
- Prefer proper abstractions and dedicated modules over quick if-else patches
- Every fix is an opportunity to create reusable infrastructure

### Paranoid Testing
- **Every commit must include tests** - no exceptions
- Tests exist to break code, not confirm it works
- Test happy path + edge cases + error scenarios + boundary conditions
- 100% network isolation - all HTTP requests mocked via global fixture
- Two basic tests are not testing - comprehensive coverage means testing every logical branch

### Code Quality Standards (Mandatory)
- **Type hints**: All function parameters and return values must be typed
- **Docstrings**: Google-style with Args/Returns/Raises sections for all functions
- **Logging**: Use loguru at key decision points (INFO for business logic, DEBUG for technical)
- **Error handling**: Catch specific exceptions, never bare `except:` or `except Exception:`
- **No tech debt**: Extract hardcoded values and duplicated code immediately
- **No placeholders**: Every function must be complete and production-ready

## Project Structure

```
kiro-gateway/
├── main.py                              # Application entry point
├── kiro/                                # Main package
│   ├── __init__.py                      # Package exports
│   ├── config.py                        # Configuration and constants
│   ├── auth.py                          # Authentication manager
│   ├── cache.py                         # Model metadata cache
│   ├── model_resolver.py                # Dynamic model resolution
│   ├── http_client.py                   # HTTP client with retry logic
│   ├── routes_openai.py                 # OpenAI API endpoints
│   ├── routes_anthropic.py              # Anthropic API endpoints
│   ├── routes_dashboard.py              # Dashboard API endpoints
│   ├── routes_accounts.py               # Account management API endpoints
│   ├── routes_logs.py                   # Logs API endpoint
│   ├── converters_core.py               # Shared conversion logic
│   ├── converters_openai.py             # OpenAI format converters
│   ├── converters_anthropic.py          # Anthropic format converters
│   ├── streaming_core.py                # Shared streaming logic
│   ├── streaming_openai.py              # OpenAI streaming
│   ├── streaming_anthropic.py           # Anthropic streaming
│   ├── parsers.py                       # AWS SSE stream parsers
│   ├── thinking_parser.py               # Thinking block parser (FSM)
│   ├── models_openai.py                 # OpenAI Pydantic models
│   ├── models_anthropic.py              # Anthropic Pydantic models
│   ├── account_manager.py               # Multi-account orchestration
│   ├── account_storage.py               # Account persistence (JSON)
│   ├── failover.py                      # Automatic retry with failover
│   ├── oauth_manager.py                 # OAuth session management
│   ├── portal_oauth.py                  # Portal OAuth utilities
│   ├── dashboard_models.py              # Dashboard data models
│   ├── metrics_collector.py             # Metrics collection
│   ├── metrics_middleware.py             # Request tracking middleware
│   ├── metrics_storage.py               # SQLite metrics storage
│   ├── network_errors.py                # Network error classification
│   ├── kiro_errors.py                   # Kiro API error enhancement
│   ├── exceptions.py                    # Exception handlers
│   ├── debug_logger.py                  # Debug logging system
│   ├── debug_middleware.py              # Debug middleware
│   ├── tokenizer.py                     # Token counting (tiktoken)
│   ├── truncation_recovery.py           # Truncation recovery logic
│   ├── truncation_state.py              # Truncation state cache
│   ├── utils.py                         # Helper utilities
│   └── strategies/                      # Account selection strategies
│       ├── __init__.py                  # Strategy exports
│       ├── base_strategy.py             # Abstract base class
│       ├── sticky_strategy.py           # Cache-optimized strategy
│       ├── round_robin_strategy.py      # Throughput-optimized strategy
│       └── hybrid_strategy.py           # Intelligent weighted strategy
├── tests/                               # Test suite
│   ├── conftest.py                      # Shared fixtures
│   ├── unit/                            # Unit tests (30 test files)
│   │   ├── test_auth_manager.py
│   │   ├── test_cache.py
│   │   ├── test_config.py
│   │   ├── test_converters_anthropic.py
│   │   ├── test_converters_core.py
│   │   ├── test_converters_openai.py
│   │   ├── test_debug_logger.py
│   │   ├── test_debug_middleware.py
│   │   ├── test_exceptions.py
│   │   ├── test_http_client.py
│   │   ├── test_kiro_errors.py
│   │   ├── test_main_cli.py
│   │   ├── test_model_resolver.py
│   │   ├── test_models_anthropic.py
│   │   ├── test_models_openai.py
│   │   ├── test_network_errors.py
│   │   ├── test_parsers.py
│   │   ├── test_routes_anthropic.py
│   │   ├── test_routes_openai.py
│   │   ├── test_strategies.py
│   │   ├── test_streaming_anthropic.py
│   │   ├── test_streaming_core.py
│   │   ├── test_streaming_openai.py
│   │   ├── test_thinking_parser.py
│   │   ├── test_tokenizer.py
│   │   ├── test_truncation_recovery.py
│   │   ├── test_truncation_state.py
│   │   ├── test_vpn_proxy.py
│   │   ├── test_account_manager.py
│   │   └── test_account_storage.py
│   ├── integration/                     # Integration tests
│   │   └── test_full_flow.py
│   └── README.md                        # Test documentation
├── static/                              # Dashboard frontend
├── docs/                                # Translated documentation
├── .env.example                         # Environment configuration template
├── requirements.txt                     # Python dependencies
├── pytest.ini                           # Pytest configuration
├── Dockerfile                           # Docker build
├── docker-compose.yml                   # Docker Compose config
└── AGENTS.md                            # Comprehensive development guide
```

## Essential Commands

### Running the Server
```bash
# Default (host: 0.0.0.0, port: 9000)
python main.py

# Custom port
python main.py --port 8080

# Custom host and port
python main.py --host 127.0.0.1 --port 8080

# Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 9000
```

### Testing
```bash
# All tests
pytest

# Verbose output
pytest -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Specific test file
pytest tests/unit/test_auth_manager.py -v

# Single test function
pytest tests/unit/test_auth_manager.py::test_refresh_token_success -v

# With coverage
pytest --cov=kiro --cov-report=html

# Multi-account specific tests
pytest tests/unit/test_account_manager.py -v
pytest tests/unit/test_strategies.py -v
pytest tests/unit/test_account_storage.py -v
```

### Docker
```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop and remove
docker-compose down
```

## Architecture

### High-Level Pattern: Adapter Pattern
```
OpenAI Clients ──┐
                 ├──► Kiro Gateway ──► Kiro API (AWS CodeWhisperer)
Anthropic Clients ┘
```

### Layered Architecture
1. **Shared Infrastructure Layer** (`auth.py`, `cache.py`, `http_client.py`)
   - Cross-cutting concerns: authentication, caching, HTTP handling, utilities

2. **Core Business Logic Layer** (`converters_core.py`, `streaming_core.py`)
   - API-agnostic Kiro payload building and response parsing
   - Shared conversion and streaming logic

3. **API-Specific Adapter Layer** (`*_openai.py`, `*_anthropic.py`)
   - Thin adapters for each supported API format
   - Format-specific models, converters, routes, and streaming formatters

4. **Application Layer** (`main.py`)
   - FastAPI setup, lifecycle management, route registration

### Key Components

**KiroAuthManager** (`kiro/auth.py`):
- Handles token lifecycle with automatic refresh (10-minute threshold)
- Supports 4 auth methods: Kiro Desktop, AWS SSO OIDC, JSON files, SQLite DB
- Thread-safe with asyncio.Lock

**ModelResolver** (`kiro/model_resolver.py`):
- 4-layer resolution pipeline:
  1. Name normalization (claude-haiku-4-5 → claude-haiku-4.5)
  2. Dynamic cache lookup (from /ListAvailableModels API)
  3. Hidden models check (undocumented but functional)
  4. Pass-through (let Kiro API decide)

**KiroHttpClient** (`kiro/http_client.py`):
- Automatic retry logic for 403 (token refresh), 429 (rate limiting), 5xx errors
- Exponential backoff with configurable delays
- Per-request client instances to prevent CLOSE_WAIT leaks in streaming

**Streaming Architecture** (`streaming_*.py`):
- Core: Parses AWS SSE stream into unified `KiroEvent` objects
- Format-specific: Converts KiroEvent → OpenAI/Anthropic SSE format
- First token timeout with retry logic

**Request/Response Conversion**:
- Core layer (`converters_core.py`): Unified message and tool processing
- API adapters (`converters_openai.py`, `converters_anthropic.py`): Format translation
- Tool description handling: Moves long descriptions to system prompt

### Multi-Account Support

**AccountManager** (`kiro/account_manager.py`):
- Manages 1-100+ Kiro accounts for continuous API access
- Automatic rotation when rate limits encountered
- Per-account state tracking: available, rate-limited, invalid, disabled
- Per-model rate limit tracking
- Thread-safe with asyncio.Lock
- JSON persistence for state recovery after restarts

**Selection Strategies** (`kiro/strategies/`):

1. **Sticky Strategy** (Cache-Optimized)
   - Maintains account continuity for prompt caching benefits
   - Best for: Conversational AI, Claude Code sessions

2. **Round-Robin Strategy** (Throughput-Optimized)
   - Rotates to next account on every request
   - Best for: High-volume batch processing, maximum RPS

3. **Hybrid Strategy** (Intelligent)
   - Weighted scoring based on: health, quota remaining, failure rate, response time
   - Best for: General-purpose, production workloads

**Failover Mechanism** (`kiro/failover.py`):
```
1. Strategy selects account based on availability + algorithm
2. Attempt request with selected account
3. On success: Update last_used, reset failures, notify strategy
4. On rate limit (429): Mark limited, set cooldown, select next, retry (max 5×)
5. On auth error (401/403): Mark invalid, exclude from pool, select next
6. If all accounts unavailable: Wait for shortest cooldown or error
```

## Configuration

### Authentication Methods (choose one)
1. **JSON Credentials** (Kiro IDE): `KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"`
2. **Environment Variables**: `REFRESH_TOKEN="your_token"`
3. **SQLite Database** (kiro-cli): `KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"`

### Required Configuration
```env
# API key for gateway authentication
PROXY_API_KEY="your-secure-api-key-here"

# Choose ONE authentication method:
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"
# OR
REFRESH_TOKEN="your_refresh_token"
# OR
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"
```

### Optional Configuration
```env
KIRO_REGION="us-east-1"                    # API region
VPN_PROXY_URL="http://127.0.0.1:7890"     # For restricted networks
DEBUG_MODE="off"                           # off/errors/all
FAKE_REASONING=true                        # Extended thinking via tag injection
SERVER_PORT=9000                           # Default port
```

### Multi-Account Configuration
```env
MULTI_ACCOUNT_ENABLED=true
ACCOUNTS_FILE="~/.config/kiro-gateway/accounts.json"
ACCOUNT_STRATEGY="hybrid"                  # sticky, round-robin, or hybrid

# Rate limit settings
RATE_LIMIT_BASE_COOLDOWN_MS=60000
RATE_LIMIT_MAX_COOLDOWN_MS=300000
RATE_LIMIT_MAX_WAIT_MS=120000

# Retry settings
MAX_ACCOUNT_RETRIES=5
RETRY_BACKOFF_BASE_MS=1000
```

### Auth Type Detection
- **AWS SSO OIDC**: Auto-detected when `clientId` and `clientSecret` present
- **Kiro Desktop**: Default when only `refreshToken` available
- **Multi-Account**: Enabled via `MULTI_ACCOUNT_ENABLED=true`

## API Endpoints

### OpenAI-Compatible
- `GET /v1/models` - List available models
- `POST /v1/chat/completions` - Chat completions (streaming/non-streaming)
- Authentication: `Authorization: Bearer {PROXY_API_KEY}`

### Anthropic-Compatible
- `POST /v1/messages` - Messages API (streaming/non-streaming)
- Authentication: `x-api-key: {PROXY_API_KEY}` + `anthropic-version: 2023-06-01`

### Dashboard & Management
- `GET /` - Dashboard UI
- `GET /health` - Health check
- `GET /api/metrics` - Dashboard metrics
- `GET /api/logs` - System logs
- Account management endpoints under `/api/v1/accounts/`

## Testing Structure

### Test Organization
- `tests/unit/` - 30 unit test files covering individual components
- `tests/integration/` - End-to-end integration tests
- `tests/conftest.py` - Comprehensive fixtures

### Test Fixtures (Key Patterns)
- **Network isolation**: Global fixture blocks all real HTTP requests
- **Mock credentials**: Never use real tokens in tests
- **Comprehensive mocking**: Auth, HTTP clients, responses all mocked
- **Arrange-Act-Assert**: Standard test structure

## Commit Standards

### Conventional Commits Format
```
<type>(scope): <description>
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

### Requirements
- **CLA required**: Contributor License Agreement for all submissions
- **Tests required**: Every functional change must include tests
- **No tech debt**: Clean up as you go

## Common Debugging Scenarios

### "Improperly formed request" Error
Kiro API's most vague error - can indicate:
- Message structure problems (wrong role order, missing fields)
- Tool definition issues (invalid schemas, name length violations)
- Content format problems (malformed JSON, unsupported types)
- Authentication or permission issues

### Token Refresh Issues
- Check auth method detection (AWS SSO OIDC vs Kiro Desktop)
- Verify `SSO_REGION` matches your AWS region
- API region is always `us-east-1` (CodeWhisperer limitation)
- Check token expiration and refresh threshold (10 minutes)

### Streaming Connection Issues
- Per-request HTTP clients prevent CLOSE_WAIT leaks
- First token timeout with retry logic handles slow responses
- Check VPN/proxy configuration if in restricted network

### Multi-Account Issues
- **All Accounts Rate Limited**: Check `accounts.json` for rate limit reset times
- **Account Marked Invalid**: Check logs for auth errors (401, 403)
- **Poor Failover Performance**: Check strategy selection and health scores
- **State Persistence Issues**: Verify `accounts.json` file permissions

## Tech Stack

**Core Dependencies**:
- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server
- `httpx` - Async HTTP client
- `loguru` - Advanced logging
- `python-dotenv` - Environment management
- `tiktoken` - Token counting (OpenAI's Rust-based tokenizer)

**Testing**:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `hypothesis` - Property-based testing

## Additional Resources

- **AGENTS.md**: Comprehensive development guide (used as user rules)
- **README.md**: User-facing setup and features
- **docs/**: Translated documentation (ru, zh, es, id, pt, ja, ko)
- **.env.example**: Complete configuration template
