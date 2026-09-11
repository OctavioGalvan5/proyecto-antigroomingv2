-- Migración 002 — habilitar monitoreo de salientes toggleable por instancia.
-- Correr en Supabase Studio (SQL Editor) sobre la DB antigrooming.
-- Idempotente.

ALTER TABLE child_instances
  ADD COLUMN IF NOT EXISTS monitor_outbound BOOLEAN NOT NULL DEFAULT TRUE;
