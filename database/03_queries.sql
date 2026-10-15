-- Representative read queries. Change sample parameters to suit demo data.
SET search_path TO pawcare, public;

-- Q1: today's employee work list (Sydney calendar day).
SELECT a.booking_code, c.display_name AS customer, p.pet_name, s.service_name,
       e.display_name AS employee, w.station_code, i.planned_start_at,
       i.planned_end_at, i.state
FROM appointment_item i
JOIN appointment a USING (appointment_id)
JOIN customer c ON c.customer_id = a.customer_id
JOIN pet p USING (pet_id)
JOIN service s USING (service_id)
JOIN employee e USING (employee_id)
JOIN workstation w USING (workstation_id)
WHERE (i.planned_start_at AT TIME ZONE 'Australia/Sydney')::date =
      (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Sydney')::date
  AND i.state IN ('scheduled','in_progress')
ORDER BY i.planned_start_at, e.employee_id;

-- Q2: a service/pet/time's candidate employee-workstation pairs.
-- Search suggestions only: confirmation MUST re-check within a locking transaction.
WITH params AS (
    SELECT 1::bigint AS service_id, 1::bigint AS pet_id,
           TIMESTAMPTZ '2026-10-20 10:00:00+11' AS starts_at,
           TIMESTAMPTZ '2026-10-20 10:30:00+11' AS ends_at
)
SELECT e.employee_id, e.display_name, w.workstation_id, w.station_code
FROM params x
JOIN service s USING (service_id)
JOIN pet p ON p.pet_id = x.pet_id AND p.species = s.species
JOIN employee_service es ON es.service_id = s.service_id AND es.is_active
JOIN employee e ON e.employee_id = es.employee_id AND e.is_active
JOIN workstation w ON w.workstation_type = s.workstation_type AND w.is_active
WHERE s.is_active AND p.is_active AND e.staff_role IN ('groomer','manager')
  AND x.ends_at > x.starts_at
  AND EXISTS (
      SELECT 1 FROM employee_shift sh
      WHERE sh.employee_id = e.employee_id AND sh.starts_at <= x.starts_at AND sh.ends_at >= x.ends_at
  )
  AND NOT EXISTS (
      SELECT 1 FROM appointment_item i
      WHERE i.state IN ('scheduled','in_progress')
        AND (i.employee_id = e.employee_id OR i.workstation_id = w.workstation_id OR i.pet_id = p.pet_id)
        AND i.planned_start_at < x.ends_at AND x.starts_at < i.planned_end_at
  )
ORDER BY e.employee_id, w.workstation_id;

-- Q3: low-stock consumables, with never-stocked items included.
SELECT * FROM inventory_balance WHERE quantity_on_hand <= reorder_level
ORDER BY quantity_on_hand - reorder_level;

-- Q4: completed appointments that still have an amount due.
SELECT f.* FROM appointment_financials f
JOIN appointment_overview o USING (appointment_id)
WHERE o.overall_state = 'completed' AND f.amount_due > 0;

-- Q5: completed service value by month/project; this is NOT cash revenue.
SELECT date_trunc('month', r.actual_end_at AT TIME ZONE 'Australia/Sydney')::date AS month,
       s.service_id, s.service_name, COUNT(*) AS completed_count,
       SUM(i.agreed_price) AS completed_service_value
FROM service_record r
JOIN appointment_item i USING (appointment_item_id)
JOIN service s USING (service_id)
WHERE i.state = 'completed'
GROUP BY month, s.service_id
ORDER BY month, completed_service_value DESC;

-- Q6: customers with a completed visit but none in the last three months.
SELECT c.customer_id, c.display_name, c.phone, MAX(r.actual_end_at) AS last_visit
FROM customer c
JOIN appointment a USING (customer_id)
JOIN appointment_item i USING (appointment_id)
JOIN service_record r USING (appointment_item_id)
WHERE i.state = 'completed'
GROUP BY c.customer_id
HAVING MAX(r.actual_end_at) < CURRENT_TIMESTAMP - INTERVAL '3 months';

-- Q7: actual net cash receipts by day; refunds use their own occurrence date.
WITH cash_events AS (
    SELECT received_at AS happened_at, amount AS amount FROM payment
    UNION ALL
    SELECT refunded_at, -amount FROM refund
)
SELECT (happened_at AT TIME ZONE 'Australia/Sydney')::date AS day,
       SUM(amount) AS net_cash_receipts
FROM cash_events GROUP BY day ORDER BY day;
