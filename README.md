# ProcLogic API 

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

## Deployment

$ docker build . -t proclogic-api -f Dockerfile

make .env.prod and .env.postgres.prod

$ docker compose -f compose.yml -f compose.prod.yml up

## Alembic migration

$ alembic revision --autogenerate -m "NEW MIGRATION"
$ alembic upgrade head

## TODO

!! powerpoint !!
!! add all other endpoints !!
https://bosa.service-now.com/eprocurement?id=kb_article_view&sys_kb_id=5750575087f58a10651ec9130cbb3563
!! dynamic dns + jarvis and xcp ng !!

1. add test companies
2. add test cpv codes to cpv codes param in request to pubproc
3. make email template
4. use notice and other endpoints see postman
5. redis cache for openai/deepseek -> cache hit costs nothing?
