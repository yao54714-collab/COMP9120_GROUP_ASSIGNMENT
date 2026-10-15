-- Business rules and session support. Applied once after 01_schema.sql.
BEGIN;
CREATE EXTENSION IF NOT EXISTS btree_gist;
SET LOCAL search_path TO pawcare, public;

CREATE TABLE auth_session (
    token_hash char(64) PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES user_account(account_id),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at)
);
CREATE INDEX session_account_idx ON auth_session(account_id);

-- [start,end) permits consecutive services without an artificial one-minute gap.
ALTER TABLE appointment_item ADD CONSTRAINT no_employee_overlap EXCLUDE USING gist
    (employee_id WITH =, tstzrange(planned_start_at,planned_end_at,'[)') WITH &&)
    WHERE (state IN ('scheduled','in_progress'));
ALTER TABLE appointment_item ADD CONSTRAINT no_station_overlap EXCLUDE USING gist
    (workstation_id WITH =, tstzrange(planned_start_at,planned_end_at,'[)') WITH &&)
    WHERE (state IN ('scheduled','in_progress'));
ALTER TABLE appointment_item ADD CONSTRAINT no_pet_overlap EXCLUDE USING gist
    (pet_id WITH =, tstzrange(planned_start_at,planned_end_at,'[)') WITH &&)
    WHERE (state IN ('scheduled','in_progress'));
ALTER TABLE employee_shift ADD CONSTRAINT no_shift_overlap EXCLUDE USING gist
    (employee_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&);

CREATE FUNCTION check_appointment_item() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id bigint; animal pet; svc service;
BEGIN
    PERFORM pg_advisory_xact_lock(9120,1);
    SELECT customer_id INTO owner_id FROM appointment WHERE appointment_id=NEW.appointment_id;
    SELECT * INTO animal FROM pet WHERE pet_id=NEW.pet_id;
    SELECT * INTO svc FROM service WHERE service_id=NEW.service_id;
    IF animal.customer_id IS DISTINCT FROM owner_id THEN
        RAISE EXCEPTION 'Pet does not belong to appointment customer' USING ERRCODE='23514';
    END IF;
    IF animal.species IS DISTINCT FROM svc.species THEN
        RAISE EXCEPTION 'Pet species does not match service' USING ERRCODE='23514';
    END IF;
    IF TG_OP='UPDATE' THEN
        IF (OLD.appointment_id,OLD.pet_id,OLD.service_id,OLD.item_no) IS DISTINCT FROM
           (NEW.appointment_id,NEW.pet_id,NEW.service_id,NEW.item_no) THEN
            RAISE EXCEPTION 'Service item identity cannot be changed' USING ERRCODE='23514';
        END IF;
        IF OLD.state IN ('completed','cancelled','no_show') AND OLD IS DISTINCT FROM NEW THEN
            RAISE EXCEPTION 'Final service item is immutable' USING ERRCODE='23514';
        END IF;
        IF OLD.state IS DISTINCT FROM NEW.state AND NOT (
            (OLD.state='requested' AND NEW.state IN ('scheduled','cancelled')) OR
            (OLD.state='scheduled' AND NEW.state IN ('in_progress','cancelled','no_show')) OR
            (OLD.state='in_progress' AND NEW.state='completed')) THEN
            RAISE EXCEPTION 'Invalid service state transition' USING ERRCODE='23514';
        END IF;
        IF OLD.state IN ('in_progress','completed') AND
           (OLD.employee_id,OLD.workstation_id,OLD.planned_start_at,OLD.planned_end_at,OLD.agreed_price) IS DISTINCT FROM
           (NEW.employee_id,NEW.workstation_id,NEW.planned_start_at,NEW.planned_end_at,NEW.agreed_price) THEN
            RAISE EXCEPTION 'Started service cannot be repriced or rescheduled' USING ERRCODE='23514';
        END IF;
    END IF;
    IF NEW.state='requested' AND (NEW.employee_id IS NOT NULL OR NEW.agreed_price IS NOT NULL) THEN
        RAISE EXCEPTION 'Requested service must not reserve resources or a price' USING ERRCODE='23514';
    END IF;
    IF NEW.state IN ('requested','scheduled','in_progress') AND (NOT animal.is_active OR NOT svc.is_active) THEN
        RAISE EXCEPTION 'Inactive pet or service' USING ERRCODE='23514';
    END IF;
    IF NEW.state IN ('scheduled','in_progress') THEN
        IF NOT EXISTS (SELECT 1 FROM employee_service es JOIN employee e USING(employee_id)
                       WHERE es.employee_id=NEW.employee_id AND es.service_id=NEW.service_id AND es.is_active AND e.is_active) THEN
            RAISE EXCEPTION 'Employee lacks an active service qualification' USING ERRCODE='23514';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM workstation WHERE workstation_id=NEW.workstation_id AND is_active AND workstation_type=svc.workstation_type) THEN
            RAISE EXCEPTION 'Workstation type is unsuitable' USING ERRCODE='23514';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM employee_shift WHERE employee_id=NEW.employee_id
                       AND starts_at<=NEW.planned_start_at AND ends_at>=NEW.planned_end_at) THEN
            RAISE EXCEPTION 'Service is outside employee shift' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER appointment_item_guard BEFORE INSERT OR UPDATE ON appointment_item
    FOR EACH ROW EXECUTE FUNCTION check_appointment_item();

CREATE FUNCTION check_service_record_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item_id bigint; s text; r service_record;
BEGIN
    item_id=NEW.appointment_item_id;
    SELECT state INTO s FROM appointment_item WHERE appointment_item_id=item_id;
    SELECT * INTO r FROM service_record WHERE appointment_item_id=item_id;
    IF (s='in_progress' AND (r.appointment_item_id IS NULL OR r.actual_end_at IS NOT NULL)) OR
       (s='completed' AND (r.appointment_item_id IS NULL OR r.actual_end_at IS NULL)) OR
       (s NOT IN ('in_progress','completed') AND r.appointment_item_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Service state and care record disagree' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER item_record_consistency AFTER INSERT OR UPDATE ON appointment_item
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_service_record_state();
CREATE CONSTRAINT TRIGGER record_item_consistency AFTER INSERT OR UPDATE ON service_record
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_service_record_state();

CREATE FUNCTION immutable_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Ledger entries cannot be edited or deleted; use a new compensating entry' USING ERRCODE='23514';
END $$;
CREATE TRIGGER immutable_inventory BEFORE UPDATE OR DELETE ON inventory_movement FOR EACH ROW EXECUTE FUNCTION immutable_ledger();
CREATE TRIGGER immutable_payment BEFORE UPDATE OR DELETE ON payment FOR EACH ROW EXECUTE FUNCTION immutable_ledger();
CREATE TRIGGER immutable_refund BEFORE UPDATE OR DELETE ON refund FOR EACH ROW EXECUTE FUNCTION immutable_ledger();
CREATE TRIGGER immutable_consumption BEFORE UPDATE OR DELETE ON service_consumption FOR EACH ROW EXECUTE FUNCTION immutable_ledger();

CREATE FUNCTION check_inventory_balance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE balance numeric;
BEGIN
    PERFORM 1 FROM consumable WHERE consumable_id=NEW.consumable_id FOR UPDATE;
    SELECT COALESCE(SUM(quantity_delta),0) INTO balance FROM inventory_movement WHERE consumable_id=NEW.consumable_id;
    IF balance+NEW.quantity_delta < 0 THEN
        RAISE EXCEPTION 'Insufficient inventory; the entire transaction must roll back' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER inventory_balance_guard BEFORE INSERT ON inventory_movement FOR EACH ROW EXECUTE FUNCTION check_inventory_balance();

CREATE FUNCTION check_consumption_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m_id bigint; k text; n integer;
BEGIN
    m_id=NEW.movement_id;
    SELECT movement_kind INTO k FROM inventory_movement WHERE movement_id=m_id;
    SELECT COUNT(*) INTO n FROM service_consumption WHERE movement_id=m_id;
    IF (k='use' AND n<>1) OR (k<>'use' AND n<>0) THEN
        RAISE EXCEPTION 'A service-use movement must have exactly one service record source' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER movement_source_guard AFTER INSERT ON inventory_movement DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_consumption_source();
CREATE CONSTRAINT TRIGGER consumption_source_guard AFTER INSERT ON service_consumption DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_consumption_source();

CREATE FUNCTION check_cash_entry() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a_id bigint; due numeric; available numeric;
BEGIN
    IF TG_TABLE_NAME='payment' THEN
        a_id=NEW.appointment_id;
    ELSE
        SELECT appointment_id INTO a_id FROM payment WHERE payment_id=NEW.payment_id;
    END IF;
    PERFORM 1 FROM appointment WHERE appointment_id=a_id FOR UPDATE;
    IF TG_TABLE_NAME='payment' THEN
        SELECT amount_due INTO due FROM appointment_financials WHERE appointment_id=a_id;
        IF NEW.amount>due THEN RAISE EXCEPTION 'Payment exceeds amount due' USING ERRCODE='23514'; END IF;
    ELSE
        SELECT refund_due INTO due FROM appointment_financials WHERE appointment_id=a_id;
        SELECT p.amount-COALESCE(SUM(r.amount),0) INTO available FROM payment p
          LEFT JOIN refund r USING(payment_id) WHERE p.payment_id=NEW.payment_id GROUP BY p.payment_id;
        IF NEW.amount>due OR NEW.amount>available THEN
            RAISE EXCEPTION 'Refund exceeds refundable balance or original payment' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER payment_limit BEFORE INSERT ON payment FOR EACH ROW EXECUTE FUNCTION check_cash_entry();
CREATE TRIGGER refund_limit BEFORE INSERT ON refund FOR EACH ROW EXECUTE FUNCTION check_cash_entry();

CREATE TABLE schema_version (version integer PRIMARY KEY, installed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO schema_version(version) VALUES(1);
COMMIT;
