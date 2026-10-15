BEGIN;
SET LOCAL search_path TO pawcare, public;
CREATE OR REPLACE FUNCTION guard_identity_changes() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(9120,1);
    IF TG_TABLE_NAME='pet' THEN
        IF (OLD.customer_id,OLD.species) IS DISTINCT FROM (NEW.customer_id,NEW.species)
           AND EXISTS(SELECT 1 FROM appointment_item WHERE pet_id=OLD.pet_id) THEN
            RAISE EXCEPTION 'Pet with appointment history cannot change ownership or species' USING ERRCODE='23514';
        END IF;
    ELSIF TG_TABLE_NAME='service' THEN
        IF (OLD.species,OLD.workstation_type) IS DISTINCT FROM (NEW.species,NEW.workstation_type)
           AND EXISTS(SELECT 1 FROM appointment_item WHERE service_id=OLD.service_id) THEN
            RAISE EXCEPTION 'Referenced service type cannot change' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER pet_identity_guard BEFORE UPDATE ON pet FOR EACH ROW EXECUTE FUNCTION guard_identity_changes();
CREATE TRIGGER service_identity_guard BEFORE UPDATE ON service FOR EACH ROW EXECUTE FUNCTION guard_identity_changes();

CREATE FUNCTION protect_care_record() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s text;
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Care records cannot be deleted' USING ERRCODE='23514'; END IF;
    SELECT state INTO s FROM appointment_item WHERE appointment_item_id=OLD.appointment_item_id;
    IF s<>'in_progress' OR (OLD.appointment_item_id,OLD.actual_start_at) IS DISTINCT FROM (NEW.appointment_item_id,NEW.actual_start_at) THEN
        RAISE EXCEPTION 'Final care record or its identity is immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER care_record_guard BEFORE UPDATE OR DELETE ON service_record FOR EACH ROW EXECUTE FUNCTION protect_care_record();

CREATE OR REPLACE FUNCTION check_consumption_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m_id bigint; k text; n integer;
BEGIN
    m_id=NEW.movement_id;
    SELECT movement_kind INTO k FROM inventory_movement WHERE movement_id=m_id;
    SELECT COUNT(*) INTO n FROM service_consumption WHERE movement_id=m_id;
    IF (k='use' AND n<>1) OR (k<>'use' AND n<>0) THEN
        RAISE EXCEPTION 'A service-use movement must have exactly one service record source' USING ERRCODE='23514';
    END IF;
    IF k='use' AND NOT EXISTS(SELECT 1 FROM service_consumption sc JOIN appointment_item i ON i.appointment_item_id=sc.service_record_id
                              WHERE sc.movement_id=m_id AND i.state='completed') THEN
        RAISE EXCEPTION 'Service consumption must commit with a completed service' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END $$;

CREATE FUNCTION separate_account_roles() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM user_account WHERE account_id=NEW.account_id FOR UPDATE;
    IF TG_TABLE_NAME='employee' THEN
        IF EXISTS(SELECT 1 FROM customer_account WHERE account_id=NEW.account_id) THEN
            RAISE EXCEPTION 'Staff and customer accounts are separate' USING ERRCODE='23514';
        END IF;
    ELSE
        IF EXISTS(SELECT 1 FROM employee WHERE account_id=NEW.account_id) THEN
            RAISE EXCEPTION 'Staff and customer accounts are separate' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER employee_account_guard BEFORE INSERT OR UPDATE ON employee FOR EACH ROW EXECUTE FUNCTION separate_account_roles();
CREATE TRIGGER customer_account_guard BEFORE INSERT OR UPDATE ON customer_account FOR EACH ROW EXECUTE FUNCTION separate_account_roles();
INSERT INTO schema_version(version) VALUES(2);
COMMIT;
