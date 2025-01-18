create table descriptions (
  id bigint primary key generated always as identity,
  language text not null,
  text text not null
);

create table cpv_additional_codes (
  id bigint primary key generated always as identity,
  code text not null
);

create table cpv_additional_code_descriptions (
  cpv_additional_code_id bigint references cpv_additional_codes (id),
  description_id bigint references descriptions (id),
  primary key (cpv_additional_code_id, description_id)
);

create table cpv_main_codes (
  id bigint primary key generated always as identity,
  code text not null
);

create table enterprise_categories (
  id bigint primary key generated always as identity,
  category_code text not null,
  levels text
);

create table dossiers (
  id bigint primary key generated always as identity,
  legal_basis text not null,
  number text not null,
  procurement_procedure_type text not null,
  reference_number text not null
);

create table lots (
  id bigint primary key generated always as identity,
  reserved_execution text,
  reserved_participation text
);

create table lot_descriptions (
  lot_id bigint references lots (id),
  description_id bigint references descriptions (id),
  primary key (lot_id, description_id)
);

create table organisations (
  id bigint primary key generated always as identity,
  organisation_id bigint not null,
  tree text not null
);

create table organisation_names (
  organisation_id bigint references organisations (id),
  name_id bigint references descriptions (id),
  primary key (organisation_id, name_id)
);

create table publications (
  id bigint primary key generated always as identity,
  procedure_id text not null,
  publication_date date not null,
  dispatch_date date not null,
  insertion_date date not null,
  publication_type text not null,
  publication_workspace_id text not null,
  reference_number text not null,
  ted_published boolean not null,
  vault_submission_deadline timestamp not null,
  cpv_main_code_id bigint references cpv_main_codes (id),
  organisation_id bigint references organisations (id),
  dossier_id bigint references dossiers (id)
);
