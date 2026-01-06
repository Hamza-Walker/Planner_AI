-- Planner AI Database Schema
-- Queue Items Table for Durable Processing Queue

-- Enable UUID extension for unique IDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Queue item status enum (skip if already exists)
DO $$ BEGIN
    CREATE TYPE queue_status AS ENUM (
        'pending',      -- Waiting to be processed
        'processing',   -- Currently being processed by a worker
        'completed',    -- Successfully processed
        'failed',       -- Processing failed (will retry if attempts < max)
        'dead'          -- Exceeded max retry attempts, moved to dead letter
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Main queue table
CREATE TABLE IF NOT EXISTS queue_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Payload
    notes TEXT NOT NULL,
    
    -- Status tracking
    status queue_status NOT NULL DEFAULT 'pending',
    
    -- Retry logic
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    
    -- Energy context (captured at submission time)
    submitted_energy_price_eur NUMERIC(5,3),
    submitted_solar_available BOOLEAN,
    submitted_llm_tier VARCHAR(10),
    
    -- Processing context (filled when processed)
    processed_energy_price_eur NUMERIC(5,3),
    processed_solar_available BOOLEAN,
    processed_llm_tier VARCHAR(10),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processing_started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Worker tracking (for debugging/monitoring)
    worker_id VARCHAR(64),
    
    -- Result storage (JSON blob with extracted tasks)
    result JSONB
);

-- Indexes for efficient queue operations
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);
CREATE INDEX IF NOT EXISTS idx_queue_pending_created ON queue_items(created_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_queue_processing ON queue_items(processing_started_at) WHERE status = 'processing';

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_queue_items_updated_at ON queue_items;
CREATE TRIGGER update_queue_items_updated_at
    BEFORE UPDATE ON queue_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to safely dequeue an item (atomic operation)
-- Returns the next pending item and marks it as processing
CREATE OR REPLACE FUNCTION dequeue_item(p_worker_id VARCHAR(64))
RETURNS TABLE (
    item_id UUID,
    item_notes TEXT,
    item_attempts INTEGER,
    item_submitted_llm_tier VARCHAR(10)
) AS $$
DECLARE
    v_item_id UUID;
BEGIN
    -- Select and lock one pending item, ordered by creation time (FIFO)
    SELECT id INTO v_item_id
    FROM queue_items
    WHERE status = 'pending'
    ORDER BY created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;
    
    IF v_item_id IS NULL THEN
        RETURN;
    END IF;
    
    -- Update the item to processing status
    UPDATE queue_items
    SET 
        status = 'processing',
        processing_started_at = NOW(),
        attempts = attempts + 1,
        worker_id = p_worker_id
    WHERE id = v_item_id;
    
    -- Return the item details
    RETURN QUERY
    SELECT 
        q.id,
        q.notes,
        q.attempts,
        q.submitted_llm_tier
    FROM queue_items q
    WHERE q.id = v_item_id;
END;
$$ LANGUAGE plpgsql;

-- Function to mark an item as completed
CREATE OR REPLACE FUNCTION complete_item(
    p_item_id UUID,
    p_result JSONB,
    p_energy_price NUMERIC(5,3),
    p_solar_available BOOLEAN,
    p_llm_tier VARCHAR(10)
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE queue_items
    SET 
        status = 'completed',
        completed_at = NOW(),
        result = p_result,
        processed_energy_price_eur = p_energy_price,
        processed_solar_available = p_solar_available,
        processed_llm_tier = p_llm_tier
    WHERE id = p_item_id AND status = 'processing';
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to mark an item as failed (with retry logic)
CREATE OR REPLACE FUNCTION fail_item(
    p_item_id UUID,
    p_error TEXT
)
RETURNS VARCHAR AS $$
DECLARE
    v_attempts INTEGER;
    v_max_attempts INTEGER;
    v_new_status queue_status;
BEGIN
    SELECT attempts, max_attempts INTO v_attempts, v_max_attempts
    FROM queue_items
    WHERE id = p_item_id;
    
    IF v_attempts >= v_max_attempts THEN
        v_new_status := 'dead';
    ELSE
        v_new_status := 'pending';  -- Back to pending for retry
    END IF;
    
    UPDATE queue_items
    SET 
        status = v_new_status,
        last_error = p_error,
        processing_started_at = NULL,
        worker_id = NULL
    WHERE id = p_item_id;
    
    RETURN v_new_status::VARCHAR;
END;
$$ LANGUAGE plpgsql;

-- Function to recover stale processing items (heartbeat timeout)
-- Items stuck in 'processing' for more than the timeout are reset to 'pending'
CREATE OR REPLACE FUNCTION recover_stale_items(p_timeout_minutes INTEGER DEFAULT 5)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    WITH recovered AS (
        UPDATE queue_items
        SET 
            status = CASE 
                WHEN attempts >= max_attempts THEN 'dead'::queue_status
                ELSE 'pending'::queue_status
            END,
            processing_started_at = NULL,
            worker_id = NULL,
            last_error = 'Worker timeout - recovered'
        WHERE status = 'processing'
          AND processing_started_at < NOW() - (p_timeout_minutes || ' minutes')::INTERVAL
        RETURNING id
    )
    SELECT COUNT(*) INTO v_count FROM recovered;
    
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- View for queue statistics
CREATE OR REPLACE VIEW queue_stats AS
SELECT 
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest_item,
    MAX(created_at) as newest_item,
    AVG(attempts) as avg_attempts
FROM queue_items
GROUP BY status;

-- Comment on table
COMMENT ON TABLE queue_items IS 'Durable queue for energy-aware task processing. Items are queued when energy is expensive and processed when conditions improve.';
