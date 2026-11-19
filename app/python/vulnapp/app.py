# Deliberately vulnerable test app for the lab (SQL built by string concatenation, file path from a parameter).
# Never expose it outside the lab network.
import os
import sqlite3

from flask import Flask, request

app = Flask(__name__)
DB = "/tmp/vuln.db"
FILES = "/tmp/files"


def init():
    os.makedirs(FILES, exist_ok=True)
    with open(os.path.join(FILES, "hello.txt"), "w") as f:
        f.write("hello\n")
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS users")
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    con.executemany("INSERT INTO users VALUES (?, ?)", [(1, "alice"), (2, "bob"), (3, "carol")])
    con.commit()
    con.close()


@app.route("/health")
def health():
    return "ok"


@app.route("/user")
def user():
    uid = request.args.get("id", "")
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT id, name FROM users WHERE id = " + uid).fetchall()
    con.close()
    return {"rows": rows}


@app.route("/user_safe")
def user_safe():
    uid = request.args.get("id", "")
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT id, name FROM users WHERE id = ?", (uid,)).fetchall()
    con.close()
    return {"rows": rows}


@app.route("/file")
def file():
    name = request.args.get("name", "")
    with open(os.path.join(FILES, name)) as f:
        return f.read()
