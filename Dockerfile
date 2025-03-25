FROM python:latest

WORKDIR /code

COPY ./alembic.ini /code/alembic.ini

COPY ./alembic /code/alembic

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

# Run with Uvicorn (standard for FastAPI)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]

# If behind proxy like Nginx/Traefik:
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--proxy-headers"]
