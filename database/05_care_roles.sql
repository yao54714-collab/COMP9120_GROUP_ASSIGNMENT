-- Additive migration: preserve every existing business row and history.
BEGIN;
SET LOCAL search_path TO pawcare, public;

CREATE FUNCTION guard_employee_care_role() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(9120,1);
    IF (NEW.staff_role NOT IN ('groomer','manager') OR NOT NEW.is_active)
       AND (OLD.staff_role,OLD.is_active) IS DISTINCT FROM (NEW.staff_role,NEW.is_active)
       AND EXISTS(SELECT 1 FROM appointment_item WHERE employee_id=OLD.employee_id AND state IN ('scheduled','in_progress')) THEN
        RAISE EXCEPTION 'Employee has unfinished care tasks; finish or reassign before removing care access' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER employee_care_role_guard BEFORE UPDATE ON employee FOR EACH ROW EXECUTE FUNCTION guard_employee_care_role();

CREATE FUNCTION guard_care_qualification_role() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(9120,1);
    IF NEW.is_active AND NOT EXISTS(SELECT 1 FROM employee WHERE employee_id=NEW.employee_id AND staff_role IN ('groomer','manager')) THEN
        RAISE EXCEPTION 'Care qualification requires a groomer or manager role' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER qualification_care_role_guard BEFORE INSERT OR UPDATE ON employee_service FOR EACH ROW EXECUTE FUNCTION guard_care_qualification_role();

CREATE FUNCTION guard_assignment_care_role() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(9120,1);
    IF NEW.state IN ('scheduled','in_progress') AND NOT EXISTS(
        SELECT 1 FROM employee WHERE employee_id=NEW.employee_id AND is_active AND staff_role IN ('groomer','manager')) THEN
        RAISE EXCEPTION 'Assigned employee must have an active care role' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER assignment_care_role_guard BEFORE INSERT OR UPDATE ON appointment_item FOR EACH ROW EXECUTE FUNCTION guard_assignment_care_role();

INSERT INTO schema_version(version) VALUES(3);
COMMIT;
