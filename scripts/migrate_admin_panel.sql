-- Migration: Add admin panel columns to shops table
-- Run this on Supabase SQL Editor

-- Bot personality & customization
ALTER TABLE shops ADD COLUMN IF NOT EXISTS bot_personality VARCHAR(50) DEFAULT 'friendly';
ALTER TABLE shops ADD COLUMN IF NOT EXISTS bot_faq_custom TEXT;
ALTER TABLE shops ADD COLUMN IF NOT EXISTS promo_text TEXT;

-- Plan & limits
ALTER TABLE shops ADD COLUMN IF NOT EXISTS plan VARCHAR(20) DEFAULT 'free';
ALTER TABLE shops ADD COLUMN IF NOT EXISTS plan_conversations_limit INTEGER DEFAULT 50;
