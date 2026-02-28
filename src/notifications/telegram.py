"""Telegram notification service — sends lead cards to shop owners."""

from aiogram import Bot
import structlog

from src.schemas.lead import LeadNotification

logger = structlog.get_logger()

LEAD_TEMPLATE_RU = """🔔 <b>Новая заявка!</b>

👤 <b>Клиент:</b> {customer_name}
📞 <b>Телефон:</b> {customer_phone}
💬 <b>Telegram:</b> {customer_telegram}

📱 <b>Устройство:</b> {device_full_name}
🔧 <b>Проблема:</b> {problem_summary}
⚡ <b>Срочность:</b> {urgency}

💰 <b>Оценка:</b> {price_range}

🕐 <b>Желаемое время:</b> {preferred_time}

<i>Заявка #{lead_id} · Этапов диалога: {messages_count}</i>"""


class TelegramNotifier:
    """Sends formatted lead notifications via Telegram."""

    async def send_lead_notification(
        self,
        bot: Bot,
        owner_chat_id: int,
        notification: LeadNotification,
    ) -> bool:
        """Send a lead notification to the shop owner.

        Args:
            bot: The shop's Telegram bot instance
            owner_chat_id: Telegram chat ID of the shop owner
            notification: Lead notification data

        Returns:
            True if sent successfully
        """
        price_range = "Требуется диагностика"
        if notification.estimated_price_min and notification.estimated_price_max:
            price_range = (
                f"{notification.estimated_price_min:,.0f}"
                f"–{notification.estimated_price_max:,.0f} ₽"
            )

        urgency_map = {
            "urgent": "🔴 Срочно",
            "normal": "🟡 Стандарт",
            "flexible": "🟢 Не срочно",
        }

        text = LEAD_TEMPLATE_RU.format(
            customer_name=notification.customer_name or "Не указано",
            customer_phone=notification.customer_phone or "Не указан",
            customer_telegram=notification.customer_telegram or "Не указан",
            device_full_name=notification.device_full_name or "Не указано",
            problem_summary=notification.problem_summary or "Не описана",
            urgency=urgency_map.get(notification.urgency or "normal", "🟡 Стандарт"),
            price_range=price_range,
            preferred_time=notification.preferred_time or "Не указано",
            lead_id=notification.lead_id[:8],
            messages_count=notification.messages_count,
        )

        try:
            await bot.send_message(
                chat_id=owner_chat_id,
                text=text,
                parse_mode="HTML",
            )
            logger.info(
                "lead_notification_sent",
                owner_chat_id=owner_chat_id,
                lead_id=notification.lead_id,
            )
            return True

        except Exception as e:
            logger.error(
                "lead_notification_failed",
                error=str(e),
                owner_chat_id=owner_chat_id,
            )
            return False
