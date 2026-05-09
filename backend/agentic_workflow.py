"""
LangGraph Workflow for Agentic Systems.

Built-in tools available to every agent:
  1. search_knowledge_base  — RAG retrieval
  2. send_email             — SendGrid (sync, fixed)
  3. check_available_slots  — booking availability
  4. book_appointment       — create booking + send confirmation email
  5. cancel_appointment     — cancel booking + send cancellation email

Plus any custom webhook tools defined per-agent in the DB.
"""

import json
import logging
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool, StructuredTool
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolExecutor, ToolNode

from config import settings
import logging

logger = logging.getLogger(__name__)


# ── State Definition ──────────────────────────────────────────

class AgentState(TypedDict):
    """The state of the agent's workflow."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context_chunks: List[Dict[str, Any]]
    system_prompt: str
    agent_id: str      # injected so tools can look up DB records


from pydantic import BaseModel, Field, create_model
import httpx


class SearchInput(BaseModel):
    query: str = Field(description="The specific search query or keywords to look for in the knowledge base.")


class SendEmailInput(BaseModel):
    to_email: str = Field(description="The email address to send the message to.")
    subject: str = Field(description="The subject line of the email.")
    body: str = Field(description="The plain-text or simple HTML body of the email.")


class CheckSlotsInput(BaseModel):
    date: str = Field(description="The date to check for availability in YYYY-MM-DD format.")


class BookAppointmentInput(BaseModel):
    date: str = Field(description="Appointment date in YYYY-MM-DD format.")
    time: str = Field(description="Appointment time in HH:MM format (24-hour).")
    customer_name: str = Field(description="Full name of the customer.")
    customer_email: str = Field(description="Email address of the customer for confirmation.")
    customer_phone: str = Field(default="", description="Phone number of the customer (optional).")
    notes: str = Field(default="", description="Any additional notes about the appointment (optional).")


class CancelAppointmentInput(BaseModel):
    booking_id: str = Field(description="The UUID of the booking to cancel.")


# ── Workflow Setup ────────────────────────────────────────────

def create_agentic_workflow(retriever, api_key: str, custom_tools: list[dict] = None,
                            agent_id: str = None, agent_name: str = "AI Agent"):
    """
    Creates and returns a compiled LangGraph workflow.

    Args:
        retriever: The HybridRetriever instance to use for the knowledge base tool.
        api_key:   The Groq API key.
        custom_tools: List of custom webhook tool dicts from the DB.
        agent_id:  The agent's UUID (for DB-backed booking tools).
        agent_name: The agent's persona name (for emails).
    """

    # ── 1. Built-in Tools ─────────────────────────────────────

    @tool("search_knowledge_base", args_schema=SearchInput)
    def search_knowledge_base(query: str) -> str:
        """
        Search the agent's knowledge base for information relevant to the user's query.
        Use this tool when you need factual information, business details, or specific
        policies that might be stored in the documents.
        """
        logger.info("LangGraph: Searching knowledge base for '%s'", query)
        try:
            results = retriever.retrieve(query, top_k=5)
            if not results:
                return "No relevant information found in the knowledge base."
            formatted = []
            for res in results:
                source_name = res.get("metadata", {}).get("source", "Unknown Document")
                formatted.append(f"Source: {source_name}\nContent: {res.get('text', '')}\n")
            return "\n".join(formatted)
        except Exception as e:
            logger.error("Error in search_knowledge_base tool: %s", e)
            return "An error occurred while searching the knowledge base."

    @tool("send_email", args_schema=SendEmailInput)
    def send_email_tool(to_email: str, subject: str, body: str) -> str:
        """
        Send an email to a customer with requested information.
        Use this when the user explicitly asks to receive information via email,
        or when you need to send a summary, document, or follow-up.
        """
        logger.info("LangGraph: Sending email to '%s'", to_email)
        from email_service import EmailService
        email_svc = EmailService(from_name=agent_name)

        if not email_svc.enabled:
            return "Failed to send email — the email service is not configured."

        # Wrap plain text body in basic HTML if not already HTML
        if not body.strip().startswith("<"):
            html_body = f"<p style='font-family:Arial,sans-serif;line-height:1.6;'>{body.replace(chr(10), '<br>')}</p>"
        else:
            html_body = body

        success = email_svc.send_email_sync(to_email, subject, html_body)
        if success:
            return f"✅ Email successfully sent to {to_email}."
        return "❌ Failed to send email due to an API error. Please try again."

    @tool("check_available_slots", args_schema=CheckSlotsInput)
    def check_available_slots(date: str) -> str:
        """
        Check what appointment/booking slots are available for a given date.
        Use this when a customer asks about availability or wants to schedule an appointment.
        The date must be in YYYY-MM-DD format (e.g., 2026-05-15).
        """
        logger.info("LangGraph: Checking available slots for agent=%s date=%s", agent_id, date)
        if not agent_id:
            return "Booking system is not configured for this agent."
        try:
            from db import database as db
            slots = db.compute_available_slots(agent_id, date)
            if not slots:
                return f"No available slots on {date}. The business may be closed or fully booked."
            slot_list = ", ".join(slots)
            return f"Available slots on {date}: {slot_list}. Ask the customer which time works best."
        except Exception as e:
            logger.error("Error checking available slots: %s", e)
            return "Could not retrieve availability. Please ask the customer to call or check back later."

    @tool("book_appointment", args_schema=BookAppointmentInput)
    def book_appointment(date: str, time: str, customer_name: str, customer_email: str,
                         customer_phone: str = "", notes: str = "") -> str:
        """
        Book an appointment for a customer. Use this after the customer has chosen a time slot.
        Always confirm the date, time, and customer name before booking.
        A confirmation email will be sent automatically to the customer's email address.
        """
        logger.info("LangGraph: Booking appointment for %s on %s at %s", customer_name, date, time)
        if not agent_id:
            return "Booking system is not configured for this agent."
        try:
            from db import database as db
            # Verify slot is still available
            available = db.compute_available_slots(agent_id, date)
            if time not in available:
                return (
                    f"❌ The slot at {time} on {date} is no longer available. "
                    f"Available slots are: {', '.join(available) if available else 'none'}. "
                    "Please choose a different time."
                )

            booking = db.create_booking(agent_id, {
                "customer_name": customer_name,
                "customer_email": customer_email,
                "customer_phone": customer_phone or None,
                "booking_date": date,
                "booking_time": time,
                "notes": notes or None,
            })

            # Send confirmation email
            if customer_email:
                from email_service import EmailService
                email_svc = EmailService(from_name=agent_name)
                sent = email_svc.send_booking_confirmation_sync(
                    to_email=customer_email,
                    agent_name=agent_name,
                    customer_name=customer_name,
                    booking_date=date,
                    booking_time=time,
                    notes=notes,
                )
                if sent:
                    db.mark_booking_email_sent(booking["id"])

            email_note = f" A confirmation email has been sent to {customer_email}." if customer_email else ""
            return (
                f"✅ Appointment confirmed!\n"
                f"• Customer: {customer_name}\n"
                f"• Date: {date}\n"
                f"• Time: {time}\n"
                f"• Booking ID: {booking['id']}{email_note}"
            )
        except Exception as e:
            logger.error("Error booking appointment: %s", e)
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                return f"❌ That slot ({time} on {date}) was just taken. Please choose another time."
            return f"❌ Failed to create booking: {e}"

    @tool("cancel_appointment", args_schema=CancelAppointmentInput)
    def cancel_appointment(booking_id: str) -> str:
        """
        Cancel an existing appointment by its booking ID.
        The customer will receive a cancellation email.
        Use this when a customer asks to cancel their appointment.
        """
        logger.info("LangGraph: Cancelling booking %s", booking_id)
        if not agent_id:
            return "Booking system is not configured for this agent."
        try:
            from db import database as db
            booking = db.get_booking_by_id(booking_id)
            if not booking:
                return f"❌ Booking ID {booking_id} was not found."
            if booking.get("status") == "cancelled":
                return "This appointment is already cancelled."

            db.update_booking_status(booking_id, "cancelled")

            # Send cancellation email
            customer_email = booking.get("customer_email")
            if customer_email:
                from email_service import EmailService
                email_svc = EmailService(from_name=agent_name)
                email_svc.send_cancellation_sync(
                    to_email=customer_email,
                    agent_name=agent_name,
                    customer_name=booking.get("customer_name", "Customer"),
                    booking_date=booking.get("booking_date", ""),
                    booking_time=booking.get("booking_time", ""),
                )

            return (
                f"✅ Appointment cancelled.\n"
                f"• Date: {booking.get('booking_date')}\n"
                f"• Time: {booking.get('booking_time')}\n"
                f"• Customer: {booking.get('customer_name', 'N/A')}"
            )
        except Exception as e:
            logger.error("Error cancelling appointment: %s", e)
            return f"❌ Failed to cancel booking: {e}"

    tools = [
        search_knowledge_base,
        send_email_tool,
        check_available_slots,
        book_appointment,
        cancel_appointment,
    ]

    # ── 1.5 Dynamic Custom Webhook Tools ─────────────────────

    if custom_tools:
        for t in custom_tools:
            try:
                properties = t.get("parameters_schema", {}).get("properties", {})
                fields = {}
                for key, prop in properties.items():
                    fields[key] = (str, Field(description=prop.get("description", "")))

                ArgsModel = create_model(f"{t['name']}Args", **fields)

                def make_tool_func(tool_def):
                    def execute_tool(**kwargs) -> str:
                        logger.info("LangGraph: Executing dynamic tool '%s'", tool_def["name"])
                        try:
                            url = tool_def["webhook_url"]
                            if url.startswith("/"):
                                url = f"http://127.0.0.1:8000{url}"
                            method = tool_def.get("method", "POST").upper()
                            with httpx.Client(timeout=10) as client:
                                if method == "GET":
                                    resp = client.get(url, params=kwargs)
                                else:
                                    resp = client.post(url, json=kwargs)
                            return f"Tool returned status {resp.status_code}: {resp.text}"
                        except Exception as e:
                            logger.error("Error in dynamic tool %s: %s", tool_def["name"], e)
                            return f"Failed to execute tool due to error: {e}"
                    return execute_tool

                dynamic_tool = StructuredTool.from_function(
                    func=make_tool_func(t),
                    name=t["name"],
                    description=t["description"],
                    args_schema=ArgsModel,
                )
                tools.append(dynamic_tool)
            except Exception as e:
                logger.error("Failed to load dynamic tool %s: %s", t.get("name"), e)

    tool_node = ToolNode(tools)

    # ── 2. Setup LLM ──────────────────────────────────────────

    llm = ChatGroq(
        api_key=api_key or settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=0.2,
    )
    llm_with_tools = llm.bind_tools(tools)

    # ── 3. Define Nodes ───────────────────────────────────────

    def agent_node(state: AgentState):
        """The main LLM node that decides whether to answer or use a tool."""
        messages = state["messages"]
        system_prompt = state.get("system_prompt", "You are a helpful assistant.")

        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + list(messages)

        logger.info("LangGraph: Agent node executing")
        try:
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error("Groq API Error during agent node: %s", e)
            try:
                fallback_llm = ChatGroq(
                    api_key=api_key or settings.GROQ_API_KEY,
                    model_name="llama-3.1-8b-instant",
                    temperature=0.2,
                )
                fallback_msg = list(messages) + [
                    SystemMessage(content=(
                        "Warning: Your tools failed due to an API error. "
                        "Answer the user directly to the best of your ability without using tools. "
                        "If you don't know the exact answer, politely say so."
                    ))
                ]
                response = fallback_llm.invoke(fallback_msg)
                return {"messages": [response]}
            except Exception as inner_e:
                logger.error("Fallback LLM also failed: %s", inner_e)
                return {"messages": [AIMessage(content=(
                    "I'm sorry, I encountered an internal system error. "
                    "Please try again later."
                ))]}

    # ── 4. Define Edges ───────────────────────────────────────

    def should_continue(state: AgentState) -> str:
        """Route to tools if the LLM requested them, otherwise end."""
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    # ── 5. Assemble Graph ─────────────────────────────────────

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()
