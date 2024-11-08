create table notices (
  id bigint primary key generated always as identity,
  document_url_lot json,
  procedure_type text,
  classification_cpv json,
  publication_number text,
  contract_nature json,
  publication_date text,
  links json,
  notice_title json,
  tender_value_cur json,
  tender_value json,
  organisation_contact_point_tenderer json
);