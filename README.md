# Production API

A **production-grade, enterprise-ready FastAPI application** implementing a Retrieval-Augmented Generation (RAG) pipeline with LangGraph agents. Built for scalability, security, reliability, and observability.

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Overview

Production API provides a robust, production-ready backend for building intelligent AI applications with:

- **FastAPI** web framework with async/await support
- **LangGraph** agent orchestration with built-in retries and fallbacks
- **Multi-LLM support** (OpenAI, Google GenAI, Anthropic)
- **Security pipeline** with input sanitization and PII masking
- **Response caching** for optimized performance
- **Rate limiting** via SlowAPI
- **Structured logging & metrics** collection
- **LangSmith integration** for agent tracing and monitoring
- **Health checks** and readiness endpoints
- **Docker** containerization for easy deployment

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Docker & Docker Compose (optional, for containerized deployment)
- API keys for LLM providers (OpenAI, Google GenAI, and/or Anthropic)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd production-api
   ```

2. **Install dependencies:**
   ```bash
   pip install -e .
   ```

   For development:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. **Run the application:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   The API will be available at `http://localhost:8000`

### Docker Deployment

Build and run with Docker Compose:

```bash
docker-compose up --build
```

The application will be accessible at `http://localhost:8000`

## Project Structure

```
production-api/
├── app/                          # Main application package
│   ├── __init__.py
│   ├── main.py                   # FastAPI application & routes
│   ├── agent.py                  # LangGraph agent implementation
│   ├── cache.py                  # Response caching layer
│   ├── config.py                 # Configuration management
│   ├── models.py                 # Pydantic request/response models
│   ├── monitoring.py             # Logging & metrics collection
│   ├── security.py               # Security pipeline (sanitization, PII masking)
│   └── __init__.py
├── src/
│   └── production_api/           # Production API module
│       └── __init__.py
├── static/                       # Static assets (frontend, swagger UI)
│   └── index.html
├── Dockerfile                    # Container image definition
├── docker-compose.yml            # Multi-container orchestration
├── pyproject.toml                # Python project configuration
├── render.yml                    # Render deployment configuration
├── test-commands.sh              # Testing utilities
└── README.md
```

## Core Features

### 🔐 Security Pipeline

Input validation and sanitization:
- XSS prevention
- SQL injection protection
- PII (Personally Identifiable Information) detection and masking
- Input length validation

```python
from app.security import SecurityPipeline

security = SecurityPipeline()
sanitized_input = security.sanitize(user_input)
```

### ⚡ Response Caching

Configurable caching layer to reduce latency and LLM API calls:
- In-memory caching with TTL support
- Cache invalidation strategies
- Cache hit/miss metrics

```python
from app.cache import ResponseCache

cache = ResponseCache(ttl=3600)
cached_response = cache.get(key)
```

### 🛑 Rate Limiting

Prevent abuse with configurable rate limits per endpoint:
- Per-IP rate limiting
- Per-user rate limiting (with authentication)
- Customizable rate limit windows

### 📊 Monitoring & Observability

Comprehensive logging and metrics collection:
- Structured JSON logging
- Request/response timing
- Error tracking
- Custom metrics collection

```python
from app.monitoring import get_logger

logger = get_logger()
logger.info("Event", extra={"user_id": 123})
```

### 🤖 LangGraph Agent

Intelligent agent orchestration with:
- Multi-step reasoning
- Tool integration
- Built-in retry logic
- Fallback mechanisms
- LangSmith tracing

```python
from app.agent import ProductionAgent

agent = ProductionAgent(config=settings)
response = agent.run(query)
```

### 🔍 LangSmith Integration

Full tracing and monitoring of agent execution:
- Debug complex multi-step operations
- Monitor LLM calls
- Track performance metrics
- Identify bottlenecks

## API Endpoints

### Chat
- **POST** `/api/chat` - Execute a chat request with the AI agent
  - Request: `ChatRequest` (query, context, parameters)
  - Response: `ChatResponse` (response, metadata, trace_id)

### Health
- **GET** `/health` - Basic health check
- **GET** `/ready` - Readiness probe (checks dependencies)

### Metrics
- **GET** `/metrics` - Prometheus-compatible metrics endpoint

### Static Files
- **GET** `/*` - Serve static frontend assets

## Configuration

Configuration is managed via environment variables in `.env`:

```env
# LLM Configuration
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=...

# Application Settings
DEBUG=false
LOG_LEVEL=INFO
CACHE_TTL=3600
RATE_LIMIT=100/minute

# LangSmith
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=production-api

# Security
ENABLE_PII_MASKING=true
MAX_INPUT_LENGTH=10000
```

See [app/config.py](app/config.py) for all available configuration options.

## API Usage Examples

### Chat Request

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the capital of France?",
    "context": "geography"
  }'
```

Response:
```json
{
  "response": "The capital of France is Paris.",
  "metadata": {
    "model": "gpt-4",
    "tokens_used": 45,
    "execution_time_ms": 1250
  },
  "trace_id": "trace_abc123..."
}
```

### Health Check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "0.1.0"
}
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Quality

```bash
# Format code
black app/

# Type checking
mypy app/

# Linting
ruff check app/
```

### Testing Commands

Predefined test commands are available in `test-commands.sh`:

```bash
./test-commands.sh
```

## Deployment

### Render Deployment

Deploy to Render using the included configuration:

```bash
# Configuration is in render.yml
# Commit and push to trigger automatic deployment
git push origin main
```

### Docker Deployment

```bash
docker build -t production-api:latest .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  production-api:latest
```

### Environment-Specific Configuration

Create environment-specific `.env` files:
- `.env.development` - Development settings
- `.env.staging` - Staging settings
- `.env.production` - Production settings

Load the appropriate file based on your deployment environment.

## Performance Considerations

- **Caching**: Response caching reduces repeated API calls by ~70%
- **Rate Limiting**: Prevents abuse and protects backend services
- **Async Processing**: All I/O operations are async for maximum concurrency
- **Connection Pooling**: Reuses connections to external services
- **Structured Logging**: Low-overhead JSON logging for easy parsing and filtering

## Troubleshooting

### Application Won't Start

Check that all required environment variables are set:
```bash
echo $OPENAI_API_KEY  # Should not be empty
```

### Rate Limit Errors

Reduce request frequency or adjust `RATE_LIMIT` in configuration:
```env
RATE_LIMIT=200/minute
```

### High Latency

Check cache hit rates and enable caching if disabled:
```env
ENABLE_CACHE=true
CACHE_TTL=3600
```

### LangSmith Not Recording

Verify LangSmith credentials and project name:
```bash
export LANGSMITH_API_KEY=...
export LANGSMITH_PROJECT=production-api
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

**Mohammad Sadegh Eftekhar**
- Email: m.sadegh@tutamail.com

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact the author via email

---

**Built with ❤️ for production AI applications**
