$ python3 -m venv .venv
$ .venv/bin/pip install -r requirements.txt
$ ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 9005 --reload
$ source .venv/bin/activate.fish
