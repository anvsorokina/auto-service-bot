"""Conversation Engine — the main dialog orchestrator.

Routes user messages to the correct step handler,
manages state transitions, saves every message to DB,
and creates leads on completion.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.conversation.session import SessionManager
from src.conversation.steps.base import BaseStep, StepResult
from src.conversation.steps.contact_info import ContactInfoStep
from src.conversation.steps.device_model import DeviceModelStep
from src.conversation.steps.device_type import DeviceTypeStep
from src.conversation.steps.estimate import EstimateStep
from src.conversation.steps.greeting import GreetingStep
from src.conversation.steps.problem import ProblemStep
from src.llm.unified import current_shop_config, process_message
from src.bot.factory import get_or_create_bot
from src.models.conversation import Conversation, Message
from src.models.lead import Appointment, Lead
from src.notifications.telegram import TelegramNotifier
from src.pricing.engine import PricingEngine
from src.schemas.conversation import ConversationStep, SessionState
from src.schemas.lead import LeadNotification

logger = structlog.get_logger()

# Step registry (APPOINTMENT step removed — handled via text in ESTIMATE)
STEP_HANDLERS: dict[str, BaseStep] = {
    ConversationStep.GREETING.value: GreetingStep(),
    ConversationStep.DEVICE_TYPE.value: DeviceTypeStep(),
    ConversationStep.DEVICE_MODEL.value: DeviceModelStep(),
    ConversationStep.PROBLEM.value: ProblemStep(),
    ConversationStep.CONTACT_INFO.value: ContactInfoStep(),
    ConversationStep.ESTIMATE.value: EstimateStep(),
}

MAX_HISTORY = 6  # Keep last 3 exchanges (Redis sliding window for LLM)

# Human-readable labels for callback buttons
CALLBACK_LABELS: dict[str, dict[str, str]] = {
    # "device:" prefix now carries car brand values from the greeting keyboard
    "device": {
        "Toyota": "Toyota",
        "BMW": "BMW",
        "Mercedes": "Mercedes",
        "Hyundai": "Hyundai",
        "Kia": "Kia",
        "Volkswagen": "Volkswagen",
        "Lada": "Lada / ВАЗ",
        "other": "Другая марка",
    },
    "problem": {
        "engine_repair": "Двигатель",
        "brake_repair": "Тормоза",
        "oil_change": "Замена масла / ТО",
        "suspension_repair": "Подвеска",
        "diagnostics": "Диагностика",
        "bodywork": "Кузов / покраска",
        "electrical": "Электрика",
        "ac_repair": "Кондиционер",
        "transmission": "Коробка передач",
        "tire_service": "Шины / колёса",
        "custom": "Другое",
        "other": "Другое",
    },
}


class ConversationEngine:
    """Main orchestrator for the intake dialog."""

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
    ) -> StepResult:
        """Process incoming user message and return bot response."""
        _config_token = current_shop_config.set(self.shop_config)
        try:
            return await self._handle_message_inner(
                shop_id, user_id, message_text, user_telegram_username, channel
            )
        finally:
            current_shop_config.reset(_config_token)

    async def handle_callback(
        self,
        shop_id: str,
        user_id: str,
        callback_data: str,
    ) -> StepResult:
        """Process inline keyboard callback."""
        _config_token = current_shop_config.set(self.shop_config)
        try:
            return await self._handle_callback_inner(shop_id, user_id, callback_data)
        finally:
            current_shop_config.reset(_config_token)

    # ─── Core message handler ────────────────────────────────────────

    async def _handle_message_inner(
        self,
        shop_id: str,
        user_id: str,
        message_text: str,
        user_telegram_username: Optional[str] = None,
        channel: str = "telegram",
    ) -> StepResult:
        """Inner message handler (ContextVar already set by handle_message)."""
        lower_text = message_text.lower().strip()

        # ── /start — new or restart (checked BEFORE human mode!) ──
        if lower_text in ("/start", "start", "начать"):
            # Mark old conversation as abandoned (if exists)
            old_state = await self.session_manager.get(shop_id, user_id)
            if old_state:
                await self._update_conversation_status(
                    old_state.conversation_id, "abandoned"
                )

            await self.session_manager.delete(shop_id, user_id)
            state = await self._create_new_session(shop_id, user_id, channel=channel)
            await self.session_manager.save(shop_id, user_id, state)

            handler = STEP_HANDLERS[ConversationStep.GREETING.value]
            result = await handler.get_initial_message(state)

            # Save /start + greeting to DB
            await self._save_message_to_db(state.conversation_id, "user", "/start", step_name="greeting")
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="greeting")

            return result

        # ── "мастер" — handoff to human ──
        if self._is_master_request(lower_text):
            state = await self.session_manager.get(shop_id, user_id)
            response_text = (
                "Сейчас позову мастера — он ответит в течение 30 минут. "
                "Если будут ещё вопросы, пишите!"
            )

            if state:
                conv_id = state.conversation_id
                await self._save_message_to_db(conv_id, "user", message_text, step_name="handoff")
                await self._save_message_to_db(conv_id, "bot", response_text, step_name="handoff")
                await self._update_conversation_status(conv_id, "handoff")

            await self.session_manager.delete(shop_id, user_id)
            return StepResult(
                response_text=response_text,
                next_step=ConversationStep.COMPLETED.value,
            )

        # ── Human mode check — save message but don't reply ──
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
                    # Also update last_message_at so master sees it
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
                    return StepResult(response_text="")

        # ── Get or create session ──
        state = await self.session_manager.get(shop_id, user_id)
        if state is None:
            state = await self._create_new_session(shop_id, user_id, channel=channel)
            await self.session_manager.save(shop_id, user_id, state)

            handler = STEP_HANDLERS[ConversationStep.GREETING.value]
            result = await handler.get_initial_message(state)

            # Save first visit message + greeting
            await self._save_message_to_db(state.conversation_id, "user", message_text, step_name="greeting")
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="greeting")

            return result

        # ── Completed state — LLM follow-up ──
        if state.current_step == ConversationStep.COMPLETED:
            llm_result = await process_message(
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

            return StepResult(response_text=response_text)

        # ── Skip ──
        if lower_text in ("пропустить", "skip"):
            return await self._advance_step(state, shop_id, user_id)

        # ── Normal step processing ──
        current = state.current_step.value
        handler = STEP_HANDLERS.get(current)

        if handler is None:
            logger.warning("unknown_step", step=current)
            return StepResult(
                response_text="Что-то пошло не так. Начнём сначала — /start",
            )

        # Record user message in Redis history (for LLM context)
        state.message_history.append({"role": "user", "text": message_text})

        # Process the message through the step handler
        result = await handler.process(message_text, state)

        # Apply any partial data extracted by the step handler regardless of intent.
        # This is critical for the greeting step: when the user writes "у меня стартер
        # не крутит" the LLM can't find a brand yet (intent stays on the greeting), but
        # it DOES extract problem_description/problem_category.  We must persist those
        # so that on the very next message ("ниссан хтерра 2007") the engine already
        # has the problem saved and can jump straight to estimate.
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

            # Save to DB
            await self._save_message_to_db(state.conversation_id, "user", message_text, step_name=current)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name=current)
            await self._update_conversation_in_db(state)

            return result

        # update_data was already applied above (before the intent check)

        # Advance to next step
        if result.next_step:
            state.current_step = ConversationStep(result.next_step)

            # Lookup pricing before showing estimate and save lead early
            if result.next_step == ConversationStep.ESTIMATE.value:
                await self._lookup_pricing(state)
                await self._save_lead(
                    state, user_id, user_telegram_username, status="pending"
                )

            # Attach keyboard / initial message from next step
            if result.next_step != ConversationStep.COMPLETED.value:
                next_handler = STEP_HANDLERS.get(result.next_step)
                if next_handler:
                    next_result = await next_handler.get_initial_message(state)

                    # For ESTIMATE step: always append the price estimate
                    if result.next_step == ConversationStep.ESTIMATE.value and next_result.response_text:
                        combined_text = result.response_text or ""
                        if combined_text:
                            combined_text += "\n\n" + next_result.response_text
                        else:
                            combined_text = next_result.response_text
                        result = StepResult(
                            response_text=combined_text,
                            keyboard=next_result.keyboard,
                            next_step=result.next_step,
                            intent=result.intent,
                        )
                    elif next_result.keyboard:
                        result = StepResult(
                            response_text=result.response_text,
                            keyboard=next_result.keyboard,
                            next_step=result.next_step,
                            intent=result.intent,
                        )
                    elif not result.response_text and next_result.response_text:
                        result = StepResult(
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
        if state.current_step == ConversationStep.COMPLETED:
            if state.lead_id:
                await self._update_lead_status(state, "new")
            else:
                await self._save_lead(
                    state, user_id, user_telegram_username, status="new"
                )

        logger.info(
            "message_processed",
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
    ) -> StepResult:
        """Inner callback handler (ContextVar already set)."""
        state = await self.session_manager.get(shop_id, user_id)
        if state is None:
            return StepResult(response_text="Сессия истекла. Напишите /start")

        prefix, _, value = callback_data.partition(":")

        # Save callback as user message (human-readable label)
        callback_label = self._callback_to_label(callback_data)
        step_before = state.current_step.value

        if prefix == "device":
            # "device:" callbacks now carry car brand names from the greeting keyboard.
            # We store them as device_brand and advance directly to the model/type step.
            state.collected.device_category = "car"
            if value == "other":
                # User chose "Другая марка" — ask them to type it
                state.current_step = ConversationStep.DEVICE_TYPE
                await self.session_manager.save(shop_id, user_id, state)
                response = "Напишите марку вашего автомобиля:"
                await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
                await self._save_message_to_db(state.conversation_id, "bot", response, step_name="device_type")
                await self._update_conversation_in_db(state)
                return StepResult(response_text=response)
            # Known brand selected — store it and show model shortcuts
            state.collected.device_brand = value
            state.current_step = ConversationStep.DEVICE_TYPE
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[ConversationStep.DEVICE_TYPE.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="device_type")
            await self._update_conversation_in_db(state)
            return result

        elif prefix == "brand":
            # Legacy "brand:" callbacks — kept for backwards compatibility
            state.collected.device_brand = value
            if value == "other":
                state.current_step = ConversationStep.DEVICE_MODEL
                await self.session_manager.save(shop_id, user_id, state)
                response = "Напишите марку и модель вашего автомобиля:"
                await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
                await self._save_message_to_db(state.conversation_id, "bot", response, step_name="device_model")
                await self._update_conversation_in_db(state)
                return StepResult(response_text=response)
            state.current_step = ConversationStep.DEVICE_MODEL
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[ConversationStep.DEVICE_MODEL.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="device_model")
            await self._update_conversation_in_db(state)
            return result

        elif prefix == "model":
            if value == "custom":
                brand = state.collected.device_brand or "автомобиля"
                response = f"Напишите модель вашего {brand} (и год, если знаете):"
                await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
                await self._save_message_to_db(state.conversation_id, "bot", response, step_name="device_model")
                return StepResult(response_text=response)
            state.collected.device_model = value
            state.current_step = ConversationStep.PROBLEM
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[ConversationStep.PROBLEM.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="problem")
            await self._update_conversation_in_db(state)
            return result

        elif prefix == "problem":
            if value == "custom":
                response = "Опишите проблему своими словами:"
                await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
                await self._save_message_to_db(state.conversation_id, "bot", response, step_name="problem")
                return StepResult(response_text=response)
            state.collected.problem_category = value

            # After problem → estimate (lookup pricing + save lead)
            state.current_step = ConversationStep.ESTIMATE
            await self._lookup_pricing(state)
            await self._save_lead(
                state, user_id=user_id,
                user_telegram_username=None, status="pending",
            )
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS[ConversationStep.ESTIMATE.value]
            result = await handler.get_initial_message(state)

            await self._save_message_to_db(state.conversation_id, "user", callback_label, step_name=step_before)
            await self._save_message_to_db(state.conversation_id, "bot", result.response_text, step_name="estimate")
            await self._update_conversation_in_db(state)
            return result

        logger.warning("unknown_callback", data=callback_data)
        return StepResult(response_text="Не понял. Попробуйте ещё раз.")

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
                "save_message_error",
                error=str(e),
                conversation_id=conversation_id,
                role=role,
            )
            try:
                await self.db.rollback()
            except Exception:
                pass

    # ─── Helper: update conversation record ──────────────────────────

    async def _update_conversation_in_db(self, state: SessionState) -> None:
        """UPDATE Conversation row with current step, counts, and collected data."""
        if not self.db:
            return
        try:
            collected = state.collected
            now = datetime.now(timezone.utc)
            await self.db.execute(
                sa_update(Conversation)
                .where(Conversation.id == uuid.UUID(state.conversation_id))
                .values(
                    current_step=state.current_step.value,
                    messages_count=state.messages_count,
                    last_message_at=now,
                    device_category=collected.device_category,
                    device_brand=collected.device_brand,
                    device_model=collected.device_model,
                    problem_description=collected.problem_description,
                    problem_category=collected.problem_category,
                    urgency=collected.urgency,
                    customer_name=collected.customer_name,
                    customer_phone=collected.customer_phone,
                    preferred_time=collected.preferred_time,
                    estimated_price_min=collected.estimated_price_min,
                    estimated_price_max=collected.estimated_price_max,
                )
            )
            await self.db.flush()
        except Exception as e:
            logger.warning(
                "update_conversation_error",
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
                "update_conversation_status_error",
                error=str(e),
                conversation_id=conversation_id,
                status=status,
            )

    # ─── Helper: callback to human label ─────────────────────────────

    def _callback_to_label(self, callback_data: str) -> str:
        """Convert callback_data like 'device:smartphone' → '[Выбрано: Смартфон]'."""
        prefix, _, value = callback_data.partition(":")
        labels = CALLBACK_LABELS.get(prefix, {})
        label = labels.get(value, value)
        return f"[Выбрано: {label}]"

    # ─── Helper: detect master/operator handoff request ───────────────

    @staticmethod
    def _is_master_request(lower_text: str) -> bool:
        """Return True if the message is a request to talk to a human master.

        Uses two-signal approach: if the message contains BOTH a person-word
        (мастер/оператор/... in any grammatical form) AND an action-word
        (хочу/позовите/поговорить/...), it's a handoff request.
        Word order doesn't matter.

        Also matches exact single-word commands: мастер, оператор, etc.
        """
        # Exact one-word matches
        exact = {"мастер", "оператор", "человек", "master", "operator",
                 "менеджер", "специалист", "консультант"}
        if lower_text in exact:
            return True

        # Person-words: all case forms (мастер/мастера/мастеру/мастером/мастере)
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

        # Both signals present → handoff request (order doesn't matter)
        if has_person and has_action:
            return True

        # Single-signal: "позовите мастера" / "мастера позовите" is strong enough
        # but "мастер сказал" is NOT. So we only fire on person-word alone
        # if it looks like a command (short message with just the person-word).
        words = lower_text.split()
        if len(words) <= 3 and has_person:
            return True

        return False

    # ─── Step advance (for "skip") ───────────────────────────────────

    async def _advance_step(
        self, state: SessionState, shop_id: str, user_id: str
    ) -> StepResult:
        """Skip current step and go to the next one."""
        steps = list(ConversationStep)
        current_idx = steps.index(state.current_step)
        if current_idx + 1 < len(steps):
            state.current_step = steps[current_idx + 1]
            if state.current_step == ConversationStep.ESTIMATE:
                await self._lookup_pricing(state)
            await self.session_manager.save(shop_id, user_id, state)
            handler = STEP_HANDLERS.get(state.current_step.value)
            if handler:
                return await handler.get_initial_message(state)
        return StepResult(response_text="Спасибо! Если появятся вопросы — напишите.")

    # ─── Pricing lookup ──────────────────────────────────────────────

    async def _lookup_pricing(self, state: SessionState) -> None:
        """Lookup pricing from DB and populate estimated_price_min/max in state."""
        if not self.db:
            return
        try:
            collected = state.collected
            pricing = PricingEngine()
            estimate = await pricing.estimate(
                db=self.db,
                shop_id=state.shop_id,
                repair_type_slug=collected.problem_category,
                device_brand=collected.device_brand,
                device_model=collected.device_model,
            )

            if estimate.tiers:
                collected.estimated_price_min = min(t.price_min for t in estimate.tiers)
                collected.estimated_price_max = max(t.price_max for t in estimate.tiers)
                collected.price_confidence = estimate.confidence
                logger.info(
                    "pricing_lookup_ok",
                    shop_id=state.shop_id,
                    price_min=collected.estimated_price_min,
                    price_max=collected.estimated_price_max,
                    confidence=estimate.confidence,
                )
            else:
                logger.info(
                    "pricing_lookup_no_match",
                    shop_id=state.shop_id,
                    problem=collected.problem_category,
                    brand=collected.device_brand,
                )
        except Exception as e:
            logger.warning("pricing_lookup_error", error=str(e), shop_id=state.shop_id)

    # ─── Lead creation (DB) ──────────────────────────────────────────

    async def _save_lead(
        self,
        state: SessionState,
        user_id: str,
        user_telegram_username: Optional[str] = None,
        status: str = "new",
    ) -> None:
        """Create Lead record + update Conversation status.

        Conversation already exists in DB (created at /start).
        Messages are already being saved individually.
        """
        if not self.db:
            logger.warning("no_db_session", action="save_lead")
            return

        try:
            collected = state.collected
            now = datetime.now(timezone.utc)

            logger.info(
                "save_lead_start",
                shop_id=state.shop_id,
                conversation_id=state.conversation_id,
                device_brand=collected.device_brand,
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
                    device_category=collected.device_category,
                    device_brand=collected.device_brand,
                    device_model=collected.device_model,
                    problem_description=collected.problem_description,
                    problem_category=collected.problem_category,
                    urgency=collected.urgency,
                    customer_name=collected.customer_name,
                    customer_phone=collected.customer_phone,
                    preferred_time=collected.preferred_time,
                    estimated_price_min=collected.estimated_price_min,
                    estimated_price_max=collected.estimated_price_max,
                    messages_count=state.messages_count,
                    completed_at=now if status == "new" else None,
                    last_message_at=now,
                )
            )

            # Fallback: if conversation wasn't created yet (old session before deploy)
            if result.rowcount == 0:
                logger.info("conversation_not_found_creating", conversation_id=state.conversation_id)
                conversation = Conversation(
                    id=uuid.UUID(state.conversation_id),
                    shop_id=uuid.UUID(state.shop_id),
                    channel=state.channel,
                    external_user_id=user_id,
                    status=conv_status,
                    current_step=state.current_step.value,
                    device_category=collected.device_category,
                    device_brand=collected.device_brand,
                    device_model=collected.device_model,
                    problem_description=collected.problem_description,
                    problem_category=collected.problem_category,
                    urgency=collected.urgency,
                    customer_name=collected.customer_name,
                    customer_phone=collected.customer_phone,
                    preferred_time=collected.preferred_time,
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

            # Create Lead
            device_parts = [collected.device_brand or "", collected.device_model or ""]
            device_full_name = " ".join(p for p in device_parts if p).strip() or None

            # Channel-aware contact identifier
            if state.channel == "whatsapp":
                customer_contact = f"wa:{user_id}"
            else:
                customer_contact = user_telegram_username or f"tg:{user_id}"

            lead = Lead(
                shop_id=uuid.UUID(state.shop_id),
                conversation_id=uuid.UUID(state.conversation_id),
                customer_name=collected.customer_name,
                customer_phone=collected.customer_phone,
                customer_telegram=customer_contact,
                device_category=collected.device_category,
                device_full_name=device_full_name,
                problem_summary=collected.problem_description or collected.problem_category,
                urgency=collected.urgency or "normal",
                estimated_price_min=collected.estimated_price_min,
                estimated_price_max=collected.estimated_price_max,
                status=status,
            )
            self.db.add(lead)
            await self.db.flush()

            state.lead_id = str(lead.id)

            # Create Appointment if preferred_time is set
            if collected.preferred_time:
                scheduled = self._parse_preferred_time(collected.preferred_time)
                if scheduled:
                    appointment = Appointment(
                        shop_id=uuid.UUID(state.shop_id),
                        lead_id=lead.id,
                        scheduled_at=scheduled,
                        duration_minutes=60,
                        status="pending",
                    )
                    self.db.add(appointment)
                    await self.db.flush()
                    logger.info(
                        "appointment_created",
                        lead_id=str(lead.id),
                        scheduled_at=scheduled.isoformat(),
                    )

            logger.info(
                "lead_created",
                lead_id=str(lead.id),
                shop_id=state.shop_id,
                device=device_full_name,
                customer=collected.customer_name,
                status=status,
            )

            # Send notification to shop owner
            await self._notify_owner(lead, state, device_full_name)

        except Exception as e:
            import traceback
            logger.error(
                "save_lead_error",
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
        state: SessionState,
        device_full_name: Optional[str],
    ) -> None:
        """Send Telegram notification to the shop owner about a new lead."""
        config = self.shop_config or {}
        owner_id = config.get("owner_telegram_id")
        bot_token = config.get("telegram_bot_token")

        if not owner_id or not bot_token:
            return

        try:
            collected = state.collected
            notification = LeadNotification(
                lead_id=str(lead.id),
                customer_name=collected.customer_name,
                customer_phone=collected.customer_phone,
                device_full_name=device_full_name,
                problem_summary=collected.problem_description or collected.problem_category,
                urgency=collected.urgency,
                estimated_price_min=collected.estimated_price_min,
                estimated_price_max=collected.estimated_price_max,
                preferred_time=collected.preferred_time,
                messages_count=state.messages_count,
            )

            bot = await get_or_create_bot(bot_token)
            notifier = TelegramNotifier()
            await notifier.send_lead_notification(bot, owner_id, notification)
        except Exception as e:
            logger.error("owner_notification_error", error=str(e), shop_id=state.shop_id)

    # ─── Time parsing ─────────────────────────────────────────────────

    def _parse_preferred_time(self, text: str) -> Optional[datetime]:
        """Parse preferred_time text into a datetime using shop timezone.

        Handles patterns like:
          - "сегодня в 17:00", "сегодня в 17"
          - "завтра в 10:00", "завтра в 10"
          - "17:00", "17"
          - ISO formats
        Returns None if parsing fails.
        """
        import re as _re
        from zoneinfo import ZoneInfo

        text = text.lower().strip()

        # Use shop timezone for "today"/"tomorrow" calculations
        tz_name = (self.shop_config or {}).get("timezone", "Europe/Moscow")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now = datetime.now(tz)

        # Determine day
        if "завтра" in text:
            day = now.date() + timedelta(days=1)
        elif "послезавтра" in text:
            day = now.date() + timedelta(days=2)
        else:
            day = now.date()  # default to today

        # Extract hour:minute
        m = _re.search(r"(\d{1,2})[:\.](\d{2})", text)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
        else:
            m = _re.search(r"в\s*(\d{1,2})", text)
            if m:
                hour, minute = int(m.group(1)), 0
            else:
                m = _re.search(r"^(\d{1,2})$", text.strip())
                if m:
                    hour, minute = int(m.group(1)), 0
                else:
                    return None

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        try:
            # Create datetime in shop timezone, then convert to UTC for storage
            local_dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
            return local_dt.astimezone(timezone.utc)
        except ValueError:
            return None

    # ─── Lead status update ──────────────────────────────────────────

    async def _update_lead_status(
        self, state: SessionState, new_status: str
    ) -> None:
        """Update an existing lead's status (e.g. pending → new).

        Also syncs customer_name/phone to the Lead (collected after lead creation)
        and updates the conversation record to 'completed'.
        """
        if not self.db or not state.lead_id:
            return

        try:
            now = datetime.now(timezone.utc)
            collected = state.collected

            # Update lead status + customer info (name/phone collected AFTER lead was created)
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

            # Update conversation to completed
            conv_values: dict = {"status": "completed", "completed_at": now}
            if collected.preferred_time:
                conv_values["preferred_time"] = collected.preferred_time
            await self.db.execute(
                sa_update(Conversation)
                .where(Conversation.id == uuid.UUID(state.conversation_id))
                .values(**conv_values)
            )

            # Create Appointment if preferred_time is set
            if collected.preferred_time:
                scheduled = self._parse_preferred_time(collected.preferred_time)
                if scheduled:
                    appointment = Appointment(
                        shop_id=uuid.UUID(state.shop_id),
                        lead_id=uuid.UUID(state.lead_id),
                        scheduled_at=scheduled,
                        duration_minutes=60,
                        status="pending",
                    )
                    self.db.add(appointment)

            await self.db.flush()

            logger.info(
                "lead_status_updated",
                lead_id=state.lead_id,
                new_status=new_status,
                customer_name=collected.customer_name,
                shop_id=state.shop_id,
            )
        except Exception as e:
            logger.error(
                "update_lead_status_error",
                error=str(e),
                lead_id=state.lead_id,
                shop_id=state.shop_id,
            )

    # ─── Session creation ────────────────────────────────────────────

    async def _create_new_session(
        self, shop_id: str, user_id: str, channel: str = "telegram"
    ) -> SessionState:
        """Create a new session state AND insert Conversation row in DB."""
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Insert Conversation record immediately
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
                    "conversation_created",
                    conversation_id=conversation_id,
                    shop_id=shop_id,
                    user_id=user_id,
                    channel=channel,
                )
            except Exception as e:
                logger.error(
                    "create_conversation_error",
                    error=str(e),
                    conversation_id=conversation_id,
                )
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        return SessionState(
            conversation_id=conversation_id,
            shop_id=shop_id,
            channel=channel,
        )

    # ─── Redis history trimming ──────────────────────────────────────

    def _trim_history(self, state: SessionState) -> None:
        """Keep only the last MAX_HISTORY messages (for LLM context window)."""
        if len(state.message_history) > MAX_HISTORY:
            state.message_history = state.message_history[-MAX_HISTORY:]
