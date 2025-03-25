FROM python:latest

WORKDIR /code

COPY ./alembic.ini /code/alembic.ini

COPY ./alembic /code/alembic

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

EXPOSE 80

CMD ["gunicorn", "app.main:proclogic", "--host", "0.0.0.0", "--port", "80"]
