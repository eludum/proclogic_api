create table publications (
  id bigint primary key generated always as identity,
  reference_number text,
  insertion_date timestamp,
  organisation_id bigint,
  cancelled_at timestamp,
  dossier_id bigint,
  publication_workspace_id text,
  cpv_main_code_id bigint,
  natures jsonb,
  dispatch_date timestamp,
  sent_at jsonb,
  published_at jsonb,
  vault_submission_deadline timestamp,
  ted_published boolean,
  notice_sub_type text,
  procedure_id text
);

create table organisations (
  id bigint primary key generated always as identity,
  tree text
);

create table organisation_names (
  id bigint primary key generated always as identity,
  organisation_id bigint references organisations (id),
  text text,
  language text
);

create table dossiers (
  id bigint primary key generated always as identity,
  titles jsonb,
  descriptions jsonb,
  accreditations jsonb,
  reference_number text,
  procurement_procedure_type text,
  special_purchasing_technique text,
  legal_basis text
);

create table lots (
  id bigint primary key generated always as identity,
  titles jsonb,
  descriptions jsonb,
  reserved_participation jsonb,
  reserved_execution jsonb,
  publication_id bigint references publications (id)
);

create table cpv_codes (
  id bigint primary key generated always as identity,
  code text,
  descriptions jsonb,
  publication_id bigint references publications (id)
);

create table publication_language_association (
  publication_id bigint references publications (id),
  language text
);

create table nuts_code_association (
  publication_id bigint references publications (id),
  nuts_code text
);

create table notice_id_association (
  publication_id bigint references publications (id),
  notice_id text
);