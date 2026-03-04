"""BuildConversationEngine — main dialog orchestrator for construction intake.

Routes user messages to the correct step handler,
manages state transitions, saves every message to DB,
and creates leads on completion.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.conversation.session import SessionManager
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult
from src.products.inbuild.steps.greeting import BuildGreetingStep
from src.products.inbuild.steps.service_type import ServiceTypeStep
from src.products.inbuild.steps.property_info import PropertyInfoStep
from src.products.inbuild.steps.project_description import ProjectDescriptionStep
from src.products.inbuild.steps.timeline_budget import TimelineBudgetStep
from src.products.inbuild.steps.estimate import BuildEstimateStep
from src.products.inbuild.steps.contact_info import BuildContactInfoStep
from src.products.inbuild.schemas import BuildStep, BuildSessionState
from src.products.inbuild.constants import (
    SERVICE_LABELS,
    PROPERTY_LABELS,
    SCOPE_LABELS,
    TIMELINE_LABELS,
)
from src.products.inbuild.llm import process_build_message, current_build_shop_config
from src.bot.factory import get_or_create_bot
from src.models.conversation import Conversation, Message
from src.models.lead import Lead
from src.config import settings
from src.notifications.telegram import TelegramNotifier
from src.schemas.lead import LeadNotification

logger = structlog.get_logger()

# Step registry mapping BuildStep values to handler instances
STEP_HANDLERS: dict[str, BuildBaseStep] = {
    BuildStep.GREETING.value: BuildGreetingStep(),
    BuildStep.SERVICE_TYPE.value: ServiceTypeStep(),
    BuildStep.PROPERTY_INFO.value: PropertyInfoStep(),
    BuildStep.PROJECT_DESCRIPTION.value: ProjectDescriptionStep(),
    BuildStep.TIMELINE_BUDGET.value: TimelineBudgetStep(),
    BuildStep.ESTIMATE.value: BuildEstimateStep(),
    BuildStep.CONTACT_INFO.value: BuildContactInfoStep(),
}

MAX_HISTORY = 6  # Keep last 3 exchanges (sliding window for LLM context)

# Human-readable labels for construction callback buttons
CALLBACK_LABELS: dict[str, dict[str, str]] = {
    "service": SERVICE_LABELS,
    "property": PROPERTY_LABELS,
    "scope": SCOPE_LABELS,
    "timeline": TIMELINE_LABELS,
}


class BuildConversationEngine:
    """Main orchestrator for the construction intake dialog."""

    def __init__(
        self,
        session_manager: SessionManager,
        shop_config: Optional[dict] = None,
        db: Optional[AsyncSession] = None,
    ):
        self.session_manager = session_manager
        self.shop_config = shop_config
        self.db = db

    # ─── Public entry points ─────────────────────────────────────────

    async def handle_message(
        self,
        shop_id: str,
        user_id: str,
        message_text: str,
        user_telegram_username: Optional[str] = None,
        channel: str = "telegram",
    ) -> BuildStepResult:
        """Process incoming user message and return bot response."""
        _config_token = current_build_shop_config.set(self.shop_config)
        try:
            return await self._handle_message_inner(
                shop_id, user_id, message_text, user_telegram_username, channel
            )
        finally:
            current_build_shop_config.reset(_config_token)

    async def handle_callback(
        self,
        shop_id: str,
        user_id: str,
        callback_data: str,
    ) -> BuildStepResult:
        """Process inline keyboard callback."""
        _config_token = current_build_shop_config.set(self.shop_config)
        try:
            return await self._handle_callback_inner(shop_id, user_id, callback_data)
        finally:
            current_build_shop_config.reset(_config_token)

    # ─── Core message handler ────────────────────────────────────────

    async def _handle_message_inner(
        self,
        shop_id: str,
        user_id: str,
        message_text: str,
        user_telegram_username: Optional[str] = None,
        channel: str = "telegram",
    ) -> BuildStepResult:
        """Inner message handler (ContextVar already set by handle_message)."""
        lower_text = message_text.lower().strip()

        # ── /start — new or restart (checked BEFORE human mode!) ──
        if lower_text in ("/start", "start", "начать"):
            # Mark old conversation as abandoned if one exists
            old_state = await self.session_manager.get(shop_id, user_id)
            if old_state:
                await self._update_conversation_status(
                    old_state.conversation_id, "abandoned"
                )

            await self.session_manager.delete(shop_id, user_id)
            state = await self._create_new_session(shop_id, user_id, channel=channel)
            await self.session_manager.save(shop_id, user_id, state)

            handler = STEP_HANDLERS[BuildStep.GREETING.value]
            result = await handler.get_initial_message(state)

            # Save /start + greeting to DB
            await self._save_message_to_db(state.conversation_id, "user", "/start", step_name="greeting")
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="greeting")

            return result

        # ── "мастер" — handoff to human ──
        if self._is_master_request(lower_text):
            state = await self.session_manager.get(shop_id, user_id)
            response_text = (
                "Сейчас свяжу со специалистом — он ответит в течение 30 минут. "
                "Если появятся вопросы, пишите!"
            )

            if state:
                conv_id = state.conversation_id
                await self._save_message_to_db(conv_id, "user", message_text, step_name="handoff")
                await self._save_message_to_db(conv_id, "bot", response_text, step_name="handoff")
                await self._update_conversation_status(conv_id, "handoff")

            await self.session_manager.delete(shop_id, user_id)
            return BuildStepResult(
                response_text=response_text,
                next_step=BuildStep.COMPLETED.value,
            )

        # ── Human mode check — save message but don't auto-reply ──
        if self.db:
            from sqlalchemy import select as sa_select
            state_for_mode = await self.session_manager.get(shop_id, user_id)
            if state_for_mode:
                conv_result = await self.db.execute(
                    sa_select(Conversation.mode).where(
                        Conversation.id == uuid.UUID(state_for_mode.conversation_id)
                    )
                )
                conv_mode = conv_result.scalar_one_or_none()
                if conv_mode == "human":
                    await self._save_message_to_db(
                        state_for_mode.conversation_id,
                        "user",
                        message_text,
                        step_name="human_chat",
                    )
                    # Update last_message_at so the specialist sees new activity
                    try:
                        now = datetime.now(timezone.utc)
                        await self.db.execute(
                            sa_update(Conversation)
                            .where(Conversation.id == uuid.UUID(state_for_mode.conversation_id))
                            .values(last_message_at=now)
                        )
                        await self.db.flush()
                    except Exception as e:
                        logger.warning("human_mode_update_ts_error", error=str(e))
                    logger.info(
                        "message_silenced_human_mode",
                        shop_id=shop_id,
                        user_id=user_id,
                        conversation_id=state_for_mode.conversation_id,
                    )
                    return BuildStepResult(response_text="")

        # ── Get or create session ──
        state = await self.session_manager.get(shop_id, user_id)
        if state is None:
            state = await self._create_new_session(shop_id, user_id, channel=channel)
            await self.session_manager.save(shop_id, user_id, state)

            handler = STEP_HANDLERS[BuildStep.GREETING.value]
            result = await handler.get_initial_message(state)

            # Save first message + greeting
            await self._save_message_to_db(state.conversation_id, "user", message_text, step_name="greeting")
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="greeting")

            return result

        # ── Completed state — LLM follow-up ──
        if state.current_step == BuildStep.COMPLETED:
            llm_result = await process_build_message(
                user_message=message_text,
                step="completed",
                collected_data=state.collected.model_dump(),
                message_history=state.message_history,
                shop_config=self.shop_config,
            )
            response_text = (
                llm_result.response_text
                or "Ваша заявка уже оформлена. Напишите /start чтобы начать новую."
            )

            # Save follow-up messages
            await self._save_message_to_db(state.conversation_id, "user", message_text, step_name="completed")
            await self._save_message_to_db(state.conversation_id, "bot", response_text, step_name="completed")

            return BuildStepResult(response_text=response_text)

        # ── Skip ──
        if lower_text in ("пропустить", "skip"):
            return await self._advance_step(state, shop_id, user_id)

        # ── Normal step processing ──
        current = state.current_step.value
        handler = STEP_HANDLERS.get(current)

        if handler is None:
            logger.warning("unknown_build_step", step=current)
            return BuildStepResult(
                response_text="Что-то пошло не так. Начнём сначала — /start",
            )

        # Record user message in Redis history (for LLM context)
        state.message_history.append({"role": "user", "text": message_text})

        # Process the message through the step handler
        result = await handler.process(message_text, state)

        # Apply any partial data extracted by the step handler regardless of intent.
        # This ensures data extracted in early steps isn't lost when the LLM
        # has not yet advanced the step (e.g. service extracted during greeting).
        if result.update_data:
            for key, value in result.update_data.items():
                if hasattr(state.collected, key):
                    setattr(state.collected, key, value)

        # Intent-based routing: don't advance on questions/off-topic
        if result.intent in ("question", "off_topic"):
            state.messages_count += 1
            state.message_history.append({"role": "bot", "text": result.response_text})
            self._trim_history(state)
            await self.session_manager.save(shop_id, user_id, state)

            await self._save_message_to_db(state.conversation_id, "user", message_text, step_name=current)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name=current)
            await self._update_conversation_in_db(state)

            return result

        # Advance to next step
        if result.next_step:
            state.current_step = BuildStep(result.next_step)

            # Save lead early when approaching the estimate step
            if result.next_step == BuildStep.ESTIMATE.value:
                await self._save_lead(
                    state, user_id, user_telegram_username, status="pending"
                )

            # Attach keyboard / initial message from next step
            if result.next_step != BuildStep.COMPLETED.value:
                next_handler = STEP_HANDLERS.get(result.next_step)
                if next_handler:
                    next_result = await next_handler.get_initial_message(state)

                    # For ESTIMATE step: always append the LLM-generated estimate text
                    if result.next_step == BuildStep.ESTIMATE.value and next_result.response_text:
                        combined_text = result.response_text or ""
                        if combined_text:
                            combined_text += "\n\n" + next_result.response_text
                        else:
                            combined_text = next_result.response_text
                        result = BuildStepResult(
                            response_text=combined_text,
                            keyboard=next_result.keyboard,
                            next_step=result.next_step,
                            intent=result.intent,
                        )
                    elif next_result.keyboard:
                        result = BuildStepResult(
                            response_text=result.response_text,
                            keyboard=next_result.keyboard,
                            next_step=result.next_step,
                            intent=result.intent,
                        )
                    elif not result.response_text and next_result.response_text:
                        result = BuildStepResult(
                            response_text=next_result.response_text,
                            keyboard=next_result.keyboard,
                            next_step=result.next_step,
                            intent=result.intent,
                        )

        # Update counts and Redis history
        state.messages_count += 1
        state.message_history.append({"role": "bot", "text": result.response_text})
        self._trim_history(state)
        await self.session_manager.save(shop_id, user_id, state)

        # Save to DB
        await self._save_message_to_db(state.conversation_id, "user", message_text, step_name=current)
        await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name=state.current_step.value)
        await self._update_conversation_in_db(state)

        # Update lead status when conversation completes
        if state.current_step == BuildStep.COMPLETED:
            if state.lead_id:
                await self._update_lead_status(state, "new")
            else:
                await self._save_lead(
                    state, user_id, user_telegram_username, status="new"
                )

        logger.info(
            "build_message_processed",
            shop_id=shop_id,
            user_id=user_id,
            step=state.current_step.value,
            intent=result.intent,
            messages=state.messages_count,
        )

        return result

    # ─── Core callback handler ───────────────────────────────────────

    async def _handle_callback_inner(
        self,
        shop_id: str,
        user_id: str,
        callback_data: str,
    ) -> BuildStepResult:
        """Inner callback handler (ContextVar already set)."""
        state = await self.session_manager.get(shop_id, user_id)
        if state is None:
            return BuildStepResult(response_text="Сессия истекла. Напишите /start")

        prefix, _, value = callback_data.partition(":")

        # Save callback as a human-readable user message
        callback_label = self._callback_to_label(callback_data)
        step_before = state.current_step.value

        if prefix == "service":
            # Service category selected from greeting keyboard
            if value == "other":
                # User chose "Другое — опишу" → go to SERVICE_TYPE for free text
                state.current_step = BuildStep.SERVICE_TYPE
                await self.session_manager.save(shop_id, user_id, state)
                response = "Расскажите, какие работы нужны:"
                await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
                await self._save_message_to_db(state.conversation_id, "bot", response, step_name="service_type")
                await self._update_conversation_in_db(state)
                return BuildStepResult(response_text=response)

            # Known service category selected — store it and advance to PROPERTY_INFO
            state.collected.service_category = value
            state.current_step = BuildStep.SERVICE_TYPE
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[BuildStep.SERVICE_TYPE.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="service_type")
            await self._update_conversation_in_db(state)
            return result

        elif prefix == "property":
            # Property type selected — store it and ask for project details
            state.collected.property_type = value
            state.current_step = BuildStep.PROJECT_DESCRIPTION
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[BuildStep.PROJECT_DESCRIPTION.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="project_desc")
            await self._update_conversation_in_db(state)
            return result

        elif prefix == "scope":
            # Scope selected — store it and ask for timeline/budget
            state.collected.scope = value
            state.current_step = BuildStep.TIMELINE_BUDGET
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[BuildStep.TIMELINE_BUDGET.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="timeline_budget")
            await self._update_conversation_in_db(state)
            return result

        elif prefix == "timeline":
            # Timeline selected — store it and show the estimate
            state.collected.timeline = value
            state.current_step = BuildStep.ESTIMATE
            await self._save_lead(
                state, user_id=user_id,
                user_telegram_username=None, status="pending",
            )
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[BuildStep.ESTIMATE.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="estimate")
            await self._update_conversation_in_db(state)
            return result

        logger.warning("unknown_build_callback", data=callback_data)
        return BuildStepResult(response_text="Не понял. Попробуйте ещё раз.")

    # ─── Helper: save one message to DB ──────────────────────────────

    async def _save_message_to_db(
        self,
        conversation_id: str,
        role: str,
        content: str,
        step_name: Optional[str] = None,
    ) -> None:
        """Save a single message to the DB. Errors are logged but never break the bot."""
        if not self.db:
            return
        try:
            message = Message(
                conversation_id=uuid.UUID(conversation_id),
                role=role,
                content=content,
                step_name=step_name,
            )
            self.db.add(message)
            await self.db.flush()
        except Exception as e:
            logger.warning(
                "build_save_message_error",
                error=str(e),
                conversation_id=conversation_id,
                role=role,
            )
            try:
                await self.db.rollback()
            except Exception:
                pass

    # ─── Helper: update conversation record ──────────────────────────

    async def _update_conversation_in_db(self, state: BuildSessionState) -> None:
        """UPDATE Conversation row with current step, counts, and collected data.

        Field mapping (construction → shared Conversation columns):
          service_category  → device_category
          property_type     → device_brand
          area + address    → device_model  (combined)
          project_description → problem_description
          scope             → problem_category
        """
        if not self.db:
            return
        try:
            collected = state.collected
            now = datetime.now(timezone.utc)

            # Combine area and address into device_model column
            area_str = f"{collected.property_area_sqm} м²" if collected.property_area_sqm else ""
            address_str = collected.property_address or ""
            device_model_value = " | ".join(p for p in [area_str, address_str] if p) or None

            await self.db.execute(
                sa_update(Conversation)
                .where(Conversation.id == uuid.UUID(state.conversation_id))
                .values(
                    current_step=state.current_step.value,
                    messages_count=state.messages_count,
                    last_message_at=now,
                    device_category=collected.service_category,
                    device_brand=collected.property_type,
                    device_model=device_model_value,
                    problem_description=collected.project_description,
                    problem_category=collected.scope,
                    customer_name=collected.customer_name,
                    customer_phone=collected.customer_phone,
                    preferred_time=collected.preferred_start_date or collected.timeline,
                    estimated_price_min=collected.estimated_price_min,
                    estimated_price_max=collected.estimated_price_max,
                )
            )
            await self.db.flush()
        except Exception as e:
            logger.warning(
                "build_update_conversation_error",
                error=str(e),
                conversation_id=state.conversation_id,
            )
            try:
                await self.db.rollback()
            except Exception:
                pass

    # ─── Helper: update conversation status ──────────────────────────

    async def _update_conversation_status(
        self, conversation_id: str, status: str
    ) -> None:
        """Set conversation status (abandoned, handoff, completed)."""
        if not self.db:
            return
        try:
            now = datetime.now(timezone.utc)
            values: dict = {"status": status}
            if status in ("completed", "abandoned", "handoff"):
                values["completed_at"] = now

            await self.db.execute(
                sa_update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(**values)
            )
            await self.db.flush()
        except Exception as e:
            logger.warning(
                "build_update_conversation_status_error",
                error=str(e),
                conversation_id=conversation_id,
                status=status,
            )

    # ─── Helper: callback to human label ─────────────────────────────

    def _callback_to_label(self, callback_data: str) -> str:
        """Convert callback_data like 'service:plumbing' → '[Выбрано: Сантехника]'."""
        prefix, _, value = callback_data.partition(":")
        labels = CALLBACK_LABELS.get(prefix, {})
        label = labels.get(value, value)
        return f"[Выбрано: {label}]"

    # ─── Helper: detect master/operator handoff request ───────────────

    @staticmethod
    def _is_master_request(lower_text: str) -> bool:
        """Return True if the message is a request to talk to a human specialist.

        Uses two-signal approach: if the message contains BOTH a person-word
        (мастер/специалист/... in any grammatical form) AND an action-word
        (хочу/позовите/поговорить/...), it's a handoff request.
        Word order doesn't matter.

        Also matches exact single-word commands: мастер, оператор, etc.
        """
        # Exact one-word matches
        exact = {"мастер", "оператор", "человек", "master", "operator",
                 "менеджер", "специалист", "консультант"}
        if lower_text in exact:
            return True

        # Person-words: all case forms
        has_person = bool(re.search(
            r"мастер\w*|оператор\w*|специалист\w*|менеджер\w*|"
            r"консультант\w*|человек\w*",
            lower_text,
        ))

        # Action-words: verbs and intent markers
        has_action = bool(re.search(
            r"позови|позовите|переключи|переключите|соедини|соедините|"
            r"свяжи|свяжите|подключи|подключите|дай|дайте|"
            r"хочу|можно|нужен|нужна|нужно|давай|давайте|"
            r"поговорить|обсудить|связаться|пообщаться|побеседовать|"
            r"поговорю|обсужу|пообщаюсь|"
            r"говорить|общаться|звать|вызвать|вызови|вызовите|"
            r"попрос|жду|ждать|где\b",
            lower_text,
        ))

        # Both signals present → handoff request
        if has_person and has_action:
            return True

        # Short message (≤3 words) with a person-word alone
        words = lower_text.split()
        if len(words) <= 3 and has_person:
            return True

        return False

    # ─── Step advance (for "skip") ───────────────────────────────────

    async def _advance_step(
        self, state: BuildSessionState, shop_id: str, user_id: str
    ) -> BuildStepResult:
        """Skip current step and go to the next one."""
        steps = list(BuildStep)
        current_idx = steps.index(state.current_step)
        if current_idx + 1 < len(steps):
            state.current_step = steps[current_idx + 1]
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS.get(state.current_step.value)
            if handler:
                return await handler.get_initial_message(state)
        return BuildStepResult(response_text="Спасибо! Если появятся вопросы — напишите.")

    # ─── Lead creation (DB) ──────────────────────────────────────────

    async def _save_lead(
        self,
        state: BuildSessionState,
        user_id: str,
        user_telegram_username: Optional[str] = None,
        status: str = "new",
    ) -> None:
        """Create Lead record + update Conversation status.

        Conversation is already in DB (created at /start).
        Messages are saved individually via _save_message_to_db.

        Field mapping to shared Lead columns:
          service_category + property_type → device_category / device_full_name
          project_description              → problem_summary
          timeline                         → urgency (used as "timing" signal)
        """
        if not self.db:
            logger.warning("no_db_session", action="build_save_lead")
            return

        try:
            collected = state.collected
            now = datetime.now(timezone.utc)

            # Build a descriptive name for the project object
            property_label = PROPERTY_LABELS.get(collected.property_type or "", collected.property_type or "")
            service_label = SERVICE_LABELS.get(collected.service_category or "", collected.service_category or "")
            area_str = f"{collected.property_area_sqm:.0f} м²" if collected.property_area_sqm else ""
            device_full_name_parts = [p for p in [property_label, area_str, collected.property_address] if p]
            device_full_name = " | ".join(device_full_name_parts) or None

            # Combine area and address for device_model column
            device_model_value = " | ".join(
                p for p in [
                    f"{collected.property_area_sqm} м²" if collected.property_area_sqm else "",
                    collected.property_address or "",
                ]
                if p
            ) or None

            logger.info(
                "build_save_lead_start",
                shop_id=state.shop_id,
                conversation_id=state.conversation_id,
                service=collected.service_category,
                property_type=collected.property_type,
                customer_name=collected.customer_name,
                status=status,
            )

            # Update conversation status
            conv_status = "completed" if status == "new" else "active"
            result = await self.db.execute(
                sa_update(Conversation)
                .where(Conversation.id == uuid.UUID(state.conversation_id))
                .values(
                    status=conv_status,
                    current_step=state.current_step.value,
                    device_category=collected.service_category,
                    device_brand=collected.property_type,
                    device_model=device_model_value,
                    problem_description=collected.project_description,
                    problem_category=collected.scope,
                    customer_name=collected.customer_name,
                    customer_phone=collected.customer_phone,
                    preferred_time=collected.preferred_start_date or collected.timeline,
                    estimated_price_min=collected.estimated_price_min,
                    estimated_price_max=collected.estimated_price_max,
                    messages_count=state.messages_count,
                    completed_at=now if status == "new" else None,
                    last_message_at=now,
                )
            )

            # Fallback: if conversation wasn't created yet (old session before deploy)
            if result.rowcount == 0:
                logger.info("build_conversation_not_found_creating", conversation_id=state.conversation_id)
                conversation = Conversation(
                    id=uuid.UUID(state.conversation_id),
                    shop_id=uuid.UUID(state.shop_id),
                    channel=state.channel,
                    external_user_id=user_id,
                    status=conv_status,
                    current_step=state.current_step.value,
                    device_category=collected.service_category,
                    device_brand=collected.property_type,
                    device_model=device_model_value,
                    problem_description=collected.project_description,
                    problem_category=collected.scope,
                    customer_name=collected.customer_name,
                    customer_phone=collected.customer_phone,
                    preferred_time=collected.preferred_start_date or collected.timeline,
                    estimated_price_min=collected.estimated_price_min,
                    estimated_price_max=collected.estimated_price_max,
                    messages_count=state.messages_count,
                    started_at=now,
                    completed_at=now if status == "new" else None,
                    last_message_at=now,
                    mode="bot",
                )
                self.db.add(conversation)
                await self.db.flush()

            # Channel-aware contact identifier
            if state.channel == "whatsapp":
                customer_contact = f"wa:{user_id}"
            else:
                customer_contact = user_telegram_username or f"tg:{user_id}"

            # Map construction timeline to urgency signal for Lead
            timeline_urgency_map = {
                "asap": "urgent",
                "1_month": "normal",
                "3_months": "normal",
                "flexible": "flexible",
            }
            urgency = timeline_urgency_map.get(collected.timeline or "", "normal")

            problem_summary = (
                collected.project_description
                or collected.service_description
                or service_label
                or None
            )

            lead = Lead(
                shop_id=uuid.UUID(state.shop_id),
                conversation_id=uuid.UUID(state.conversation_id),
                customer_name=collected.customer_name,
                customer_phone=collected.customer_phone,
                customer_telegram=customer_contact,
                device_category=collected.service_category,
                device_full_name=device_full_name,
                problem_summary=problem_summary,
                urgency=urgency,
                estimated_price_min=collected.estimated_price_min,
                estimated_price_max=collected.estimated_price_max,
                status=status,
            )
            self.db.add(lead)
            await self.db.flush()

            state.lead_id = str(lead.id)

            logger.info(
                "build_lead_created",
                lead_id=str(lead.id),
                shop_id=state.shop_id,
                service=collected.service_category,
                property_type=collected.property_type,
                customer=collected.customer_name,
                status=status,
            )

            # Send notification about the new lead
            await self._notify_owner(lead, state, device_full_name, service_label)

        except Exception as e:
            import traceback
            logger.error(
                "build_save_lead_error",
                error=str(e),
                traceback=traceback.format_exc(),
                shop_id=state.shop_id,
                conversation_id=state.conversation_id,
            )
            try:
                await self.db.rollback()
            except Exception:
                pass

    # ─── Owner notification ──────────────────────────────────────────

    async def _notify_owner(
        self,
        lead: Lead,
        state: BuildSessionState,
        device_full_name: Optional[str],
        service_label: Optional[str] = None,
    ) -> None:
        """Send Telegram notification about a new construction lead."""
        bot_token = settings.notify_tg_bot_token
        chat_id = settings.notify_tg_chat_id

        if not bot_token or not chat_id:
            logger.warning("build_notify_bot_not_configured", shop_id=state.shop_id)
            return

        try:
            collected = state.collected

            problem_summary = (
                collected.project_description
                or collected.service_description
                or service_label
                or None
            )

            notification = LeadNotification(
                lead_id=str(lead.id),
                customer_name=collected.customer_name,
                customer_phone=collected.customer_phone,
                customer_telegram=lead.customer_telegram,
                device_full_name=device_full_name,
                problem_summary=problem_summary,
                urgency=lead.urgency,
                estimated_price_min=collected.estimated_price_min,
                estimated_price_max=collected.estimated_price_max,
                preferred_time=collected.preferred_start_date or collected.timeline,
                messages_count=state.messages_count,
            )

            bot = await get_or_create_bot(bot_token)
            notifier = TelegramNotifier()
            await notifier.send_lead_notification(bot, int(chat_id), notification)
        except Exception as e:
            logger.error("build_owner_notification_error", error=str(e), shop_id=state.shop_id)

    # ─── Lead status update ──────────────────────────────────────────

    async def _update_lead_status(
        self, state: BuildSessionState, new_status: str
    ) -> None:
        """Update an existing lead's status (e.g. pending → new).

        Also syncs customer_name/phone collected after lead creation,
        and marks the conversation as completed.
        """
        if not self.db or not state.lead_id:
            return

        try:
            now = datetime.now(timezone.utc)
            collected = state.collected

            # Update lead status + customer info (name/phone may arrive after lead creation)
            lead_values: dict = {"status": new_status}
            if collected.customer_name:
                lead_values["customer_name"] = collected.customer_name
            if collected.customer_phone:
                lead_values["customer_phone"] = collected.customer_phone

            await self.db.execute(
                sa_update(Lead)
                .where(Lead.id == uuid.UUID(state.lead_id))
                .values(**lead_values)
            )

            # Mark conversation completed
            conv_values: dict = {"status": "completed", "completed_at": now}
            preferred = collected.preferred_start_date or collected.timeline
            if preferred:
                conv_values["preferred_time"] = preferred
            await self.db.execute(
                sa_update(Conversation)
                .where(Conversation.id == uuid.UUID(state.conversation_id))
                .values(**conv_values)
            )

            await self.db.flush()

            logger.info(
                "build_lead_status_updated",
                lead_id=state.lead_id,
                new_status=new_status,
                customer_name=collected.customer_name,
                shop_id=state.shop_id,
            )

        except Exception as e:
            logger.error(
                "build_update_lead_status_error",
                error=str(e),
                lead_id=state.lead_id,
                shop_id=state.shop_id,
            )

    # ─── Session creation ────────────────────────────────────────────

    async def _create_new_session(
        self, shop_id: str, user_id: str, channel: str = "telegram"
    ) -> BuildSessionState:
        """Create a new session state AND insert Conversation row in DB."""
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Insert Conversation record immediately so messages can reference it
        if self.db:
            try:
                conversation = Conversation(
                    id=uuid.UUID(conversation_id),
                    shop_id=uuid.UUID(shop_id),
                    channel=channel,
                    external_user_id=user_id,
                    status="active",
                    current_step="greeting",
                    mode="bot",
                    messages_count=0,
                    started_at=now,
                    last_message_at=now,
                )
                self.db.add(conversation)
                await self.db.flush()
                logger.info(
                    "build_conversation_created",
                    conversation_id=conversation_id,
                    shop_id=shop_id,
                    user_id=user_id,
                    channel=channel,
                )
            except Exception as e:
                logger.error(
                    "build_create_conversation_error",
                    error=str(e),
                    conversation_id=conversation_id,
                )
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        return BuildSessionState(
            conversation_id=conversation_id,
            shop_id=shop_id,
            channel=channel,
        )

    # ─── Redis history trimming ──────────────────────────────────────

    def _trim_history(self, state: BuildSessionState) -> None:
        """Keep only the last MAX_HISTORY messages (for LLM context window)."""
        if len(state.message_history) > MAX_HISTORY:
            state.message_history = state.message_history[-MAX_HISTORY:]
