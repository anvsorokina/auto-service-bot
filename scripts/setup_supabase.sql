-- ============================================================
-- Repair Bot — Supabase Database Setup
-- Run this in Supabase SQL Editor (supabase.com → your project → SQL Editor)
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- SHOPS (multi-tenancy core)
-- ============================================================
CREATE TABLE IF NOT EXISTS shops (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(50) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    owner_telegram_id BIGINT,
    telegram_bot_token VARCHAR(255),
    telegram_bot_username VARCHAR(100),
    whatsapp_phone_number VARCHAR(20),
    webhook_url     VARCHAR(500),
    greeting_text   TEXT,
    language        VARCHAR(5) DEFAULT 'ru',
    timezone        VARCHAR(50) DEFAULT 'Europe/Moscow',
    currency        VARCHAR(3) DEFAULT 'RUB',
    working_hours   JSONB DEFAULT '{
        "mon": {"open": "09:00", "close": "19:00"},
        "tue": {"open": "09:00", "close": "19:00"},
        "wed": {"open": "09:00", "close": "19:00"},
        "thu": {"open": "09:00", "close": "19:00"},
        "fri": {"open": "09:00", "close": "19:00"},
        "sat": {"open": "10:00", "close": "17:00"},
        "sun": null
    }',
    collect_phone   BOOLEAN DEFAULT true,
    collect_name    BOOLEAN DEFAULT true,
    offer_appointment BOOLEAN DEFAULT true,
    bot_personality VARCHAR(50) DEFAULT 'friendly',
    bot_faq_custom  TEXT,
    promo_text      TEXT,
    plan            VARCHAR(20) DEFAULT 'free',
    plan_conversations_limit INTEGER DEFAULT 50,
    address         VARCHAR(500),
    maps_url        VARCHAR(500),
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shops_bot_token ON shops(telegram_bot_token) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_shops_owner_tg ON shops(owner_telegram_id) WHERE is_active;

-- ============================================================
-- DEVICE CATEGORIES (global reference)
-- ============================================================
CREATE TABLE IF NOT EXISTS device_categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(50) UNIQUE NOT NULL,
    name_ru         VARCHAR(100) NOT NULL,
    name_en         VARCHAR(100) NOT NULL,
    icon            VARCHAR(50)
);

INSERT INTO device_categories (slug, name_ru, name_en, icon) VALUES
('sedan', 'Легковой', 'Sedan', '🚗'),
('suv', 'Внедорожник / Кроссовер', 'SUV / Crossover', '🚙'),
('truck', 'Грузовой', 'Truck', '🚛'),
('minivan', 'Минивэн', 'Minivan', '🚐'),
('commercial', 'Коммерческий транспорт', 'Commercial', '🚚')
ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- REPAIR TYPES (global reference)
-- ============================================================
CREATE TABLE IF NOT EXISTS repair_types (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(100) UNIQUE NOT NULL,
    name_ru         VARCHAR(200) NOT NULL,
    name_en         VARCHAR(200) NOT NULL,
    device_category_id UUID REFERENCES device_categories(id),
    typical_duration_minutes INT DEFAULT 60,
    requires_part   BOOLEAN DEFAULT true
);

INSERT INTO repair_types (slug, name_ru, name_en, device_category_id, typical_duration_minutes) VALUES
('engine_repair', 'Ремонт двигателя', 'Engine Repair', (SELECT id FROM device_categories WHERE slug='sedan'), 240),
('brake_repair', 'Ремонт тормозов', 'Brake Repair', (SELECT id FROM device_categories WHERE slug='sedan'), 120),
('oil_change', 'Замена масла / ТО', 'Oil Change / Maintenance', (SELECT id FROM device_categories WHERE slug='sedan'), 60),
('suspension_repair', 'Ремонт подвески', 'Suspension Repair', (SELECT id FROM device_categories WHERE slug='sedan'), 180),
('diagnostics', 'Диагностика', 'Diagnostics', (SELECT id FROM device_categories WHERE slug='sedan'), 60),
('electrical', 'Электрика', 'Electrical', (SELECT id FROM device_categories WHERE slug='sedan'), 120),
('bodywork', 'Кузов / покраска', 'Bodywork / Paint', (SELECT id FROM device_categories WHERE slug='sedan'), 480),
('ac_repair', 'Ремонт кондиционера', 'AC Repair', (SELECT id FROM device_categories WHERE slug='sedan'), 120),
('transmission', 'Ремонт коробки передач', 'Transmission Repair', (SELECT id FROM device_categories WHERE slug='sedan'), 360),
('tire_service', 'Шины / колёса', 'Tire Service', (SELECT id FROM device_categories WHERE slug='sedan'), 60)
ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- PRICE RULES (per-shop pricing)
-- ============================================================
CREATE TABLE IF NOT EXISTS price_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id         UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    repair_type_id  UUID REFERENCES repair_types(id),
    device_brand    VARCHAR(100),
    device_model_pattern VARCHAR(200),
    price_min       DECIMAL(10,2) NOT NULL,
    price_max       DECIMAL(10,2) NOT NULL,
    tier            VARCHAR(50),
    tier_description TEXT,
    warranty_months INT DEFAULT 3,
    notes           TEXT,
    is_active       BOOLEAN DEFAULT true,
    priority        INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_rules_shop ON price_rules(shop_id, is_active);
CREATE INDEX IF NOT EXISTS idx_price_rules_brand ON price_rules(shop_id, device_brand);

-- ============================================================
-- CONVERSATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id         UUID NOT NULL REFERENCES shops(id),
    channel         VARCHAR(20) NOT NULL,
    external_user_id VARCHAR(255) NOT NULL,
    external_chat_id VARCHAR(255),
    status          VARCHAR(30) DEFAULT 'active',
    current_step    VARCHAR(50) DEFAULT 'greeting',
    device_category VARCHAR(50),
    device_brand    VARCHAR(100),
    device_model    VARCHAR(200),
    problem_description TEXT,
    problem_category VARCHAR(100),
    urgency         VARCHAR(20),
    has_previous_repair BOOLEAN,
    customer_name   VARCHAR(200),
    customer_phone  VARCHAR(50),
    preferred_time  VARCHAR(100),
    estimated_price_min FLOAT,
    estimated_price_max FLOAT,
    price_confidence VARCHAR(20),
    messages_count  INT DEFAULT 0,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,
    mode            VARCHAR(10) DEFAULT 'bot',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_shop_status ON conversations(shop_id, status);
CREATE INDEX IF NOT EXISTS idx_conversations_shop_last_msg ON conversations(shop_id, last_message_at DESC);

-- ============================================================
-- MESSAGES
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(10) NOT NULL,
    content         TEXT NOT NULL,
    llm_tokens_used INT,
    llm_model       VARCHAR(50),
    step_name       VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);

-- ============================================================
-- LEADS
-- ============================================================
CREATE TABLE IF NOT EXISTS leads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id         UUID NOT NULL REFERENCES shops(id),
    conversation_id UUID UNIQUE REFERENCES conversations(id),
    customer_name   VARCHAR(200),
    customer_phone  VARCHAR(50),
    customer_telegram VARCHAR(100),
    device_category VARCHAR(50),
    device_full_name VARCHAR(300),
    problem_summary TEXT,
    urgency         VARCHAR(20),
    estimated_price_min DECIMAL(10,2),
    estimated_price_max DECIMAL(10,2),
    status          VARCHAR(30) DEFAULT 'new',
    master_notes    TEXT,
    notification_sent BOOLEAN DEFAULT false,
    notification_sent_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_shop ON leads(shop_id, status, created_at DESC);

-- ============================================================
-- APPOINTMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS appointments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id         UUID NOT NULL REFERENCES shops(id),
    lead_id         UUID REFERENCES leads(id),
    scheduled_at    TIMESTAMPTZ NOT NULL,
    duration_minutes INT DEFAULT 60,
    status          VARCHAR(20) DEFAULT 'pending',
    reminder_sent   BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Done!
-- ============================================================
SELECT 'Database setup complete!' AS status,
       (SELECT count(*) FROM device_categories) AS device_categories,
       (SELECT count(*) FROM repair_types) AS repair_types;
