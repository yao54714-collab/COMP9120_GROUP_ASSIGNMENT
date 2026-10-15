-- Translate known legacy demo text once; preserve identities, money and history.
BEGIN;
SET LOCAL search_path TO pawcare, public;
SELECT pg_advisory_xact_lock(9120,1);
LOCK TABLE appointment, consumable, customer, employee, inventory_movement, pet, service, service_record, workstation IN ACCESS EXCLUSIVE MODE;
-- Translation-only exception for protected text. DDL and updates roll back together.
ALTER TABLE inventory_movement DISABLE TRIGGER immutable_inventory;
ALTER TABLE service_record DISABLE TRIGGER care_record_guard;
UPDATE appointment SET customer_note = CASE customer_note
    WHEN '对吹风机声音敏感，请从低档起风。' THEN 'Sensitive to dryer noise. Start with a low setting.'
    WHEN '腹部梳毛时请轻柔操作。' THEN 'Brush the belly gently.'
    WHEN '梳毛时容易紧张，请轻柔安抚。' THEN 'May become anxious during brushing. Reassure gently.'
    ELSE customer_note END WHERE customer_note IN ('对吹风机声音敏感，请从低档起风。', '腹部梳毛时请轻柔操作。', '梳毛时容易紧张，请轻柔安抚。');
UPDATE consumable SET consumable_name = CASE consumable_name
    WHEN '护理棉片' THEN 'Cotton pads'
    WHEN '温和洗毛液' THEN 'Gentle shampoo'
    WHEN '柔顺护毛素' THEN 'Conditioner'
    ELSE consumable_name END WHERE consumable_name IN ('护理棉片', '温和洗毛液', '柔顺护毛素');
UPDATE customer SET display_name = CASE display_name
    WHEN '陈晓' THEN 'Chen Xiao'
    WHEN '李安' THEN 'Li An'
    WHEN '林小雨' THEN 'Lin Xiaoyu'
    WHEN '周明' THEN 'Zhou Ming'
    WHEN '王晨' THEN 'Wang Chen'
    ELSE display_name END WHERE display_name IN ('陈晓', '李安', '林小雨', '周明', '王晨');
UPDATE employee SET display_name = CASE display_name
    WHEN '李店长' THEN 'Li (Manager)'
    WHEN '陈前台' THEN 'Chen (Reception)'
    ELSE display_name END WHERE display_name IN ('李店长', '陈前台');
UPDATE inventory_movement SET reason = CASE reason
    WHEN '演示初始入库' THEN 'Initial demo stock'
    WHEN '完成护理' THEN 'Care completed'
    ELSE reason END WHERE reason IN ('演示初始入库', '完成护理');
UPDATE pet SET pet_name = CASE pet_name
    WHEN '豆包' THEN 'Doubao'
    ELSE pet_name END WHERE pet_name IN ('豆包');
UPDATE pet SET breed = CASE breed
    WHEN '英短' THEN 'British Shorthair'
    WHEN '贵宾' THEN 'Poodle'
    WHEN '柴犬' THEN 'Shiba Inu'
    WHEN '比熊' THEN 'Bichon Frise'
    WHEN '柯基' THEN 'Corgi'
    WHEN '布偶猫' THEN 'Ragdoll'
    ELSE breed END WHERE breed IN ('英短', '贵宾', '柴犬', '比熊', '柯基', '布偶猫');
UPDATE pet SET care_notes = CASE care_notes
    WHEN '对吹风机声音敏感，请从低档起风。' THEN 'Sensitive to dryer noise. Start with a low setting.'
    WHEN '腹部梳毛时请轻柔操作。' THEN 'Brush the belly gently.'
    WHEN '梳毛时容易紧张，请轻柔安抚。' THEN 'May become anxious during brushing. Reassure gently.'
    ELSE care_notes END WHERE care_notes IN ('对吹风机声音敏感，请从低档起风。', '腹部梳毛时请轻柔操作。', '梳毛时容易紧张，请轻柔安抚。');
UPDATE service SET service_name = CASE service_name
    WHEN '猫咪温柔洗护' THEN 'Gentle cat bath'
    WHEN '猫咪精细梳毛' THEN 'Cat brushing'
    WHEN '狗狗基础洗护' THEN 'Dog bath'
    WHEN '狗狗造型修剪' THEN 'Dog trim'
    ELSE service_name END WHERE service_name IN ('猫咪温柔洗护', '猫咪精细梳毛', '狗狗基础洗护', '狗狗造型修剪');
UPDATE service_record SET care_notes = CASE care_notes
    WHEN '对吹风机声音敏感，请从低档起风。' THEN 'Sensitive to dryer noise. Start with a low setting.'
    WHEN '腹部梳毛时请轻柔操作。' THEN 'Brush the belly gently.'
    WHEN '梳毛时容易紧张，请轻柔安抚。' THEN 'May become anxious during brushing. Reassure gently.'
    ELSE care_notes END WHERE care_notes IN ('对吹风机声音敏感，请从低档起风。', '腹部梳毛时请轻柔操作。', '梳毛时容易紧张，请轻柔安抚。');
UPDATE service_record SET result_notes = CASE result_notes
    WHEN '清洁与梳毛已完成，建议日常温柔梳理。' THEN 'Bathing and brushing completed. Gentle regular brushing is recommended.'
    ELSE result_notes END WHERE result_notes IN ('清洁与梳毛已完成，建议日常温柔梳理。');
UPDATE workstation SET station_name = CASE station_name
    WHEN '洗护台 B' THEN 'Wash station B'
    WHEN '造型台 A' THEN 'Grooming station A'
    WHEN '洗护台 A' THEN 'Wash station A'
    ELSE station_name END WHERE station_name IN ('洗护台 B', '造型台 A', '洗护台 A');
-- Run deferred integrity checks before altering tables with queued trigger events.
SET CONSTRAINTS ALL IMMEDIATE;
ALTER TABLE inventory_movement ENABLE TRIGGER immutable_inventory;
ALTER TABLE service_record ENABLE TRIGGER care_record_guard;
INSERT INTO schema_version(version) VALUES(4) ON CONFLICT(version) DO NOTHING;
COMMIT;
