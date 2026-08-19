"""
Production-Ready FastAPI + LangGraph Application

Wires together:
- Security pipeline (input sanitization, PII masking)
- Response caching
- Rate limiting (slowapi)
- LangGraph agent (with retries + fallback)
- Structured logging + metrics
- LangSmith tracing
- Health checks
"""

import asyncio
import time
import os
from contextlib import asynccontextmanager, ExitStack

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from langsmith import traceable
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from dotenv import load_dotenv

from app.config import get_settings
from app.models import (
    ChatRequest, ChatResponse,
    HealthResponse, MetricsResponse, ErrorResponse,
)
from app.security import SecurityPipeline
from app.cache import ResponseCache
from app.monitoring import get_logger, MetricsCollector, RequestTimer
from app.agent import ProductionAgent

load_dotenv()



# === Global instances (initialized in lifespan) ===
security: SecurityPipeline = None
cache: ResponseCache = None
metrics: MetricsCollector = None
agent: ProductionAgent = None
logger = get_logger()


# === Lifespan (startup/shutdown) ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize all components on startup, clean up on shutdown.
    This is the modern FastAPI pattern (replaces @app.on_event).
    """
    global security, cache, metrics, agent

    settings = get_settings()

    logger.info("Starting production API...", extra={"extra_data": {
        "environment": settings.app_env,
        "primary_model": settings.primary_model,
        "tracing_enabled": settings.langchain_tracing_v2,
    }})

    # Initialize components
    security = SecurityPipeline()
    cache = ResponseCache(ttl_seconds=settings.cache_ttl_seconds)
    metrics = MetricsCollector()

    # ExitStack lets us conditionally open a Postgres connection (kept
    # alive for the app's lifetime) while still falling back cleanly to
    # plain in-memory checkpointing when DATABASE_URL isn't set.
    with ExitStack() as stack:
        if settings.database_url:
            checkpointer = stack.enter_context(
                PostgresSaver.from_conn_string(settings.database_url)
            )
            checkpointer.setup()  # idempotent — creates tables on first run
            logger.info("Persistent (Postgres) conversation memory enabled.")
        else:
            checkpointer = MemorySaver()
            logger.info("In-memory only — conversation history won't survive a restart.")

        agent = ProductionAgent(checkpointer=checkpointer)

        logger.info("All components initialized. Ready to serve requests.")

        yield  # App is running

        # Shutdown
        logger.info("Shutting down...", extra={"extra_data": metrics.summary})
    
    
    # === Rate Limiter Setup ===
limiter = Limiter(key_func=get_remote_address)

# === FastAPI App ===
app = FastAPI(
    title="Agent Console API",
    description=(
        "Chat API backing the Agent Console. Every request passes through "
        "input sanitization and PII masking, checks a response cache, then "
        "runs the LangGraph agent with automatic retries and model fallback. "
        "See /health for service status and /metrics for live performance data."
    ),
    version="1.0.0",
    contact={"name": "Mohammad Sadegh Eftekhar"},
    lifespan=lifespan,
)
app.state.limiter = limiter


# === Exception Handlers ===

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    logger.warning("Rate limit exceeded", extra={"extra_data": {
        "client_ip": get_remote_address(request),
    }})
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": "Too many requests. Please slow down.",
        },
    )


# =============================================
# ENDPOINTS
# =============================================

@app.post("/chat", response_model=ChatResponse)
@limiter.limit(get_settings().rate_limit)
@traceable(name="chat_endpoint")
async def chat(request: Request, body: ChatRequest):
    """
    Main chat endpoint.

    Flow:
    1. Security check (injection + PII masking)
    2. Cache lookup
    3. LangGraph agent invoke (if cache miss)
    4. Output validation
    5. Cache store
    6. Return response
    """
    with RequestTimer() as timer:
        security_notes = []

        # ---- Step 1: Security Check ----
        is_allowed, cleaned_message, notes = security.check_input(body.message)
        security_notes.extend(notes)

        if not is_allowed:
            logger.warning("Request blocked by security", extra={"extra_data": {
                "reason": notes,
                "thread_id": body.thread_id,
            }})
            metrics.record_request(latency_ms=0, error=True)
            raise HTTPException(
                status_code=400,
                detail="Your message was blocked by our security filters."
            )

        # ---- Step 2: Cache Lookup ----
        cached_response = cache.get(cleaned_message, thread_id=body.thread_id)
        if cached_response is not None:
            metrics.record_request(latency_ms=0, cache_hit=True)
            logger.info("Cache hit", extra={"extra_data": {
                "thread_id": body.thread_id,
            }})
            return ChatResponse(
                response=cached_response,
                thread_id=body.thread_id,
                model_used="cache",
                cached=True,
                processing_time_ms=0,
            )

        # ---- Step 3: Invoke LangGraph Agent ----
        try:
            # Runs the (synchronous) LLM + checkpoint I/O in a worker
            # thread so it doesn't block the event loop for other requests.
            result = await asyncio.to_thread(
                agent.invoke, cleaned_message, thread_id=body.thread_id
            )
        except Exception as e:
            logger.error(f"Agent invocation failed: {e}", extra={"extra_data": {
                "thread_id": body.thread_id,
                "error": str(e),
            }})
            metrics.record_request(latency_ms=0, error=True)
            raise HTTPException(
                status_code=500,
                detail="An error occurred while processing your request."
            )

        response_text = result["response"]
        model_used = result["model_used"]

        # ---- Step 4: Output Validation ----
        validated_response, output_warnings = security.check_output(response_text)
        security_notes.extend(output_warnings)

        # ---- Step 5: Cache Store ----
        cache.set(cleaned_message, validated_response, thread_id=body.thread_id)

    # ---- Step 6: Log & Record Metrics ----
    input_tokens = int(len(cleaned_message.split()) * 1.3)
    output_tokens = int(len(validated_response.split()) * 1.3)

    metrics.record_request(
        latency_ms=timer.elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_hit=False,
    )

    if security_notes:
        logger.info("Security notes", extra={"extra_data": {
            "notes": security_notes,
            "thread_id": body.thread_id,
        }})

    logger.info("Request completed", extra={"extra_data": {
        "thread_id": body.thread_id,
        "model_used": model_used,
        "latency_ms": round(timer.elapsed_ms, 2),
    }})

    return ChatResponse(
        response=validated_response,
        thread_id=body.thread_id,
        model_used=model_used,
        cached=False,
        processing_time_ms=round(timer.elapsed_ms, 2),
        security_notes=security_notes,
    )




@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check for Docker/Kubernetes."""
    settings = get_settings()

    checks = {
        "agent": agent is not None,
        "security": security is not None,
        "cache": cache is not None,
    }

    all_healthy = all(checks.values())

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        environment=settings.app_env,
        checks=checks,
    )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Metrics for monitoring dashboards."""
    summary = metrics.summary
    return MetricsResponse(**summary)


@app.get("/cache/stats")
async def cache_stats():
    """Cache performance statistics."""
    return cache.stats


# =============================================
# STATIC FRONTEND
# Mounted last so it never shadows the API routes above.
# Visiting "/" now serves the chat UI instead of a bare API root.
# =============================================
app.mount("/", StaticFiles(directory="static", html=True), name="static")