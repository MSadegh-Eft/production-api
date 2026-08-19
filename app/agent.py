"""
LangGraph Agent with Production Error Handling
Retry logic, model fallback, and structured state management.
"""

from typing import Optional
from typing_extensions import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langsmith import traceable

from app.config import get_settings


# === Agent State ===

class AgentState(TypedDict):
    """
    State for the production agent.
    Uses Annotated with add_messages reducer for message accumulation.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    error: Optional[str]
    retry_count: int
    model_used: str


# === Context-window trimming ===

def _approx_token_count(messages: list[BaseMessage]) -> int:
    """
    Rough cross-provider token estimate. Gemini and OpenAI use different
    tokenizers, so an exact count would mean calling each provider's API —
    not worth it just to decide what to trim. ~4 chars/token is the
    standard English-text rule of thumb, plus a small per-message overhead
    for role/formatting tokens.
    """
    total = 0
    for msg in messages:
        content = msg.content
        if isinstance(content, list):
            text = "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        else:
            text = content or ""
        total += len(text) // 4 + 4
    return total


def _trim_to_budget(messages: list[BaseMessage], max_tokens: int) -> list[BaseMessage]:
    """
    Drop the oldest turns until the history fits max_tokens. Always keeps
    at least the newest message, and always starts the trimmed history on
    a HumanMessage (drops in human/ai pairs) since every provider expects
    that shape.
    """
    if _approx_token_count(messages) <= max_tokens:
        return messages

    kept = list(messages)
    while len(kept) > 1 and _approx_token_count(kept) > max_tokens:
        kept.pop(0)
        if kept and isinstance(kept[0], AIMessage):
            kept.pop(0)

    return kept


# === Agent Builder ===

class ProductionAgent:
    """
    Production LangGraph agent with:
    - Retry on failure (model fallback)
    - Graceful error handling
    - LangSmith tracing
    """

    def __init__(self, checkpointer=None):
        settings = get_settings()

        self.primary_llm = ChatGoogleGenerativeAI(
            model=settings.primary_model,
            temperature=0,
            timeout=30,
            max_retries=0,
            api_key=settings.google_api_key,
        )
        self.fallback_llm = ChatOpenAI(
            model=settings.fallback_model,
            temperature=0,
            timeout=30,
            max_retries=0,
            api_key=settings.openai_api_key,
        )
        self.max_retries = settings.max_retries
        self.max_context_tokens = settings.max_context_tokens

        # Pass a checkpointer in (e.g. a PostgresSaver) for memory that
        # survives restarts. Defaults to in-process-only memory otherwise.
        self.checkpointer = checkpointer or MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
        """Build the LangGraph state machine."""

        def process_message(state: AgentState) -> dict:
            """Try to process the message with the primary model."""
            try:
                trimmed = _trim_to_budget(state["messages"], self.max_context_tokens)
                response = self.primary_llm.invoke(trimmed)
                return {
                    "messages": [response],
                    "error": None,
                    "model_used": "primary",
                }
            except Exception as e:
                return {
                    "error": str(e),
                    "retry_count": state["retry_count"] + 1,
                    "model_used": "",
                }

        def try_fallback(state: AgentState) -> dict:
            """Fallback to secondary model."""
            try:
                trimmed = _trim_to_budget(state["messages"], self.max_context_tokens)
                response = self.fallback_llm.invoke(trimmed)
                return {
                    "messages": [response],
                    "error": None,
                    "model_used": "fallback",
                }
            except Exception as e:
                return {
                    "error": str(e),
                    "model_used": "",
                }

        def handle_error(state: AgentState) -> dict:
            """Return a graceful error message."""
            return {
                "messages": [
                    AIMessage(content=(
                        "We're sorry, the agent is having trouble processing your request "
                        "right now. Please try again in a moment."
                    ))
                ],
                "model_used": "error_handler",
            }

        def route_after_process(state: AgentState) -> str:
            """Decide what to do after primary model attempt."""
            if state.get("error") is None:
                return "done"
            elif state["retry_count"] < self.max_retries:
                return "fallback"
            else:
                return "error"

        def route_after_fallback(state: AgentState) -> str:
            """Decide what to do after fallback attempt."""
            if state.get("error") is None:
                return "done"
            else:
                return "error"

        # Build the graph
        graph = StateGraph(AgentState)

        graph.add_node("process", process_message)
        graph.add_node("fallback", try_fallback)
        graph.add_node("error", handle_error)

        graph.add_edge(START, "process")
        graph.add_conditional_edges(
            "process",
            route_after_process,
            {"done": END, "fallback": "fallback", "error": "error"},
        )
        graph.add_conditional_edges(
            "fallback",
            route_after_fallback,
            {"done": END, "error": "error"},
        )
        graph.add_edge("error", END)

        return graph.compile(checkpointer=self.checkpointer)

    @traceable(name="production_agent_invoke")
    def invoke(self, message: str, thread_id: str = "default") -> dict:
        """
        Invoke the agent with a user message.

        thread_id selects which conversation's history to load and append
        to via the checkpointer — pass the same thread_id across calls to
        keep a multi-turn conversation, or a new one to start fresh.

        Returns: {"response": str, "model_used": str, "error": str | None}
        """
        config = {"configurable": {"thread_id": thread_id}}

        result = self.graph.invoke(
            {
                "messages": [HumanMessage(content=message)],
                "error": None,
                "retry_count": 0,
                "model_used": "",
            },
            config=config,
        )

        content = result["messages"][-1].content

        if isinstance(content, list):
            response = "".join(
                block["text"]
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            response = content

        return {
            "response": response,
            "model_used": result.get("model_used", "unknown"),
            "error": result.get("error"),
        }