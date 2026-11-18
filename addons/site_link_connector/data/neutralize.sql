-- A neutralized copy of a site never calls the sites it was linked to: the API keys are removed and the links archived.
UPDATE site_link SET api_key = NULL, active = false;
