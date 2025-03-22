FROM python:latest

WORKDIR /code

COPY ./alembic.ini /code/alembic.ini

COPY ./alembic /code/alembic

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

# CMD ["fastapi", "run", "app/main.py", "--port", "8000"]

# If running behind a proxy like Nginx or Traefik add --proxy-headers
CMD ["fastapi", "run", "app/main.py", "--port", "8000", "--proxy-headers"]
