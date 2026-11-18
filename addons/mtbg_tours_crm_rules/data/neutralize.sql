-- a copy of the database runs no CRM rule: the rules and the automation rules they generated are switched off
UPDATE mtbg_crm_rule SET enabled = false;
UPDATE base_automation SET active = false WHERE id IN (SELECT automation_id FROM mtbg_crm_rule WHERE automation_id IS NOT NULL);
