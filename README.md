# ProcLogic API 

## cpv codes

https://europadecentraal.nl/cpv-code-zoekmachine/#cpv-explorer-form

## Run locally

$ python3 -m venv .venv
$ source .venv/bin/activate.fish
$ pip install -r requirements.txt

make .env and .env.postgres -> see env_example and env_postgres_example

$ fastapi run app/main.py 
$ docker compose up

$ docker inspect \                               
           -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' proclogic_api-postgres-1
-> put this ip into pgadmin

## Alembic migration

$ alembic revision --autogenerate -m "NEW MIGRATION"
$ alembic upgrade head
