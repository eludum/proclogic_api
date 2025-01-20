$ python3 -m venv .venv
$ source .venv/bin/activate.fish
$ pip install -r requirements.txt
$ uvicorn main:app --host 0.0.0.0 --port 9005 --reload

# TODO

1. CRUD
2. Error handling
3. AI (Recomm & Summary)
4. Email send with final template
