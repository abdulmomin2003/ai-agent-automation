"""
LangGraph Workflow for Agentic Systems.

Defines a stateful workflow for AI agents, allowing them to:
- Use tools (like searching the knowledge base).
- Maintain conversation history.
- Produce final answers.
"""

import json
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolExecutor, ToolInvocation, ToolNode

from config import settings
import logging

logger = logging.getLogger(__name__)


# ── State Definition ──────────────────────────────────────────

class AgentState(TypedDict):
    """The state of the agent's workflow."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context_chunks: List[Dict[str, Any]]
    system_prompt: str

from pydantic import BaseModel, Field
import asyncio

class SearchInput(BaseModel):
    query: str = Field(description="The specific search query or keywords to look for in the knowledge base.")

class SendEmailInput(BaseModel):
    to_email: str = Field(description="The email address to send the message to.")
    subject: str = Field(description="The subject line of the email.")
    body: str = Field(description="The HTML body of the email. Use basic HTML tags for formatting.")

# ── Workflow Setup ────────────────────────────────────────────

def create_agentic_workflow(retriever, api_key: str):
    """
    Creates and returns a compiled LangGraph workflow.
    
    Args:
        retriever: The HybridRetriever instance to use for the knowledge base tool.
        api_key: The Groq API key.
    """

    # 1. Define Tools
    @tool("search_knowledge_base", args_schema=SearchInput)
    def search_knowledge_base(query: str) -> str:
        """
        Search the agent's knowledge base for information relevant to the user's query.
        Use this tool when you need factual information, business details, or specific 
        policies that might be stored in the documents.
        """
        logger.info(f"LangGraph: Searching knowledge base for '{query}'")
        try:
            results = retriever.retrieve(query, top_k=5)
            # Store the raw chunks to return them in the state later if needed
            # We'll just return a formatted string for the LLM to read
            if not results:
                return "No relevant information found in the knowledge base."
            
            formatted_results = []
            for i, res in enumerate(results):
                formatted_results.append(f"Source: {res['source']}\nContent: {res['text']}\n")
            
            return "\n".join(formatted_results)
        except Exception as e:
            logger.error(f"Error in search_knowledge_base tool: {e}")
            return "An error occurred while searching the knowledge base."

    @tool("send_email", args_schema=SendEmailInput)
    def send_email_tool(to_email: str, subject: str, body: str) -> str:
        """
        Send an email to a user with requested information. 
        Use this tool when the user explicitly asks to receive information via email.
        """
        logger.info(f"LangGraph: Sending email to '{to_email}'")
        from email_service import EmailService
        email_svc = EmailService(api_key=settings.SENDGRID_API_KEY)
        
        if not email_svc.enabled:
            return "Failed to send email. The email service is not configured."
            
        try:
            # We run the async email sender synchronously since the workflow invokes tools synchronously
            success = asyncio.run(email_svc.send_email(to_email, subject, body))
            if success:
                return f"Successfully sent email to {to_email}."
            return "Failed to send email due to an API error."
        except Exception as e:
            logger.error(f"Error in send_email tool: {e}")
            return f"An error occurred while sending the email."

    tools = [search_knowledge_base, send_email_tool]
    tool_executor = ToolExecutor(tools)
    tool_node = ToolNode(tools)

    # 2. Setup LLM
    llm = ChatGroq(
        api_key=api_key or settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,  # Use model from config (llama-3.3-70b-versatile)
        temperature=0.2,
    )
    llm_with_tools = llm.bind_tools(tools)

    # 3. Define Nodes
    def agent_node(state: AgentState):
        """The main LLM node that decides whether to answer or use a tool."""
        messages = state["messages"]
        system_prompt = state.get("system_prompt", "You are a helpful assistant.")
        
        # Add strict formatting instruction to prevent Llama-3 XML function hallucination
        system_prompt += "\n\nIMPORTANT: When you need to search the knowledge base, use the provided tool natively. DO NOT generate text like <function=search_knowledge_base...>. Only output the standard tool call."
        
        # Ensure system prompt is the first message
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + list(messages)

        logger.info("LangGraph: Agent node executing")
        
        try:
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"Groq API Error during tool execution: {e}")
            # Fallback to direct answer without tools to prevent the app from crashing
            try:
                fallback_llm = ChatGroq(
                    api_key=api_key or settings.GROQ_API_KEY,
                    model_name="llama-3.1-8b-instant",  # A fast, stable fallback model
                    temperature=0.2,
                )
                fallback_msg = list(messages)
                fallback_msg.append(SystemMessage(content="Warning: Your search tool failed due to an API error. Answer the user directly to the best of your ability without searching. If you don't know the exact answer, politely say so."))
                response = fallback_llm.invoke(fallback_msg)
                return {"messages": [response]}
            except Exception as inner_e:
                logger.error(f"Fallback LLM also failed: {inner_e}")
                return {"messages": [AIMessage(content="I'm sorry, I encountered an internal system error and cannot access my knowledge base right now. Please try again later.")]}

    # 4. Define Edges (Routing)
    def should_continue(state: AgentState) -> str:
        """Determine whether to continue to tools or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If the LLM made a tool call, route to 'tools'
        if getattr(last_message, "tool_calls", None):
            return "tools"
        
        # Otherwise, end
        return END

    # 5. Assemble Graph
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END,
        }
    )
    
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()
