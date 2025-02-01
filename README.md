# API 

## Build locally

$ python3 -m venv .venv
$ source .venv/bin/activate.fish
$ pip install -r requirements.txt
$ uvicorn main:app --host 0.0.0.0 --port 9005 --reload

## Deployment

$ docker build . -t proclogic-api -f Dockerfile
$ docker compose -f compose.yml -f compose.prod.yml up

## Alembic migration

$ alembic revision --autogenerate -m "NEW MIGRATION"
$ alembic upgrade head
