import time
from fastapi.testclient import TestClient
from vartani.app import app

c = TestClient(app)


def _wait(rid):
    for _ in range(200):
        m = c.get(f"/api/runs/{rid}").json()
        if m["status"] not in ("queued", "running"):
            return m
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_end_to_end_run(fake_llm):
    m = c.post("/api/models", json={"kind": "openai", "label": "fake", "base_url": fake_llm, "model": "x"}).json()
    t = c.post("/api/models/test", json={"id": m["id"]}).json()
    assert t["ok"] and t["margin_available"]
    items = c.get("/api/samples/hi_demo").json()["items"]
    run = c.post("/api/runs", json={"name": "t", "items": items, "model_id": m["id"], "config": {"scan": True}}).json()
    done = _wait(run["id"])
    assert done["status"] == "done" and done["done_items"] == 6
    rep = c.get(f"/api/runs/{run['id']}/report").json()["report"]
    assert rep["n_items"] == 6 and rep["accuracy"]["native"]["n"] == 6 and rep["fragility"]
    assert rep["verdict"]["label"]
    assert len(c.get(f"/api/runs/{run['id']}/items").json()) == 6
    assert "qid,lang,gold" in c.get(f"/api/runs/{run['id']}/export.csv").text
    assert "Vartani report" in c.get(f"/api/runs/{run['id']}/export.html").text
    c.delete(f"/api/runs/{run['id']}")


def test_unreachable_model_fails_cleanly():
    m = c.post("/api/models", json={"kind": "openai", "label": "dead", "base_url": "http://127.0.0.1:9/v1", "model": "x"}).json()
    assert c.post("/api/models/test", json={"id": m["id"]}).json()["ok"] is False


def test_import_colab_files():
    import glob
    f = sorted(glob.glob("data/paper/qwen3*_hi_*.jsonl"))[0]
    r = c.post("/api/import", files=[("files", ("a.jsonl", open(f, "rb")))]).json()
    rep = c.get(f"/api/runs/{r['id']}/report").json()["report"]
    assert rep["n_items"] == 200 and rep["accuracy"]["native"]["acc"] == 70.5


def test_parse_csv():
    r = c.post("/api/datasets/parse", json={"filename": "a.csv", "lang": "hi", "text":
        "passage,question,option_a,option_b,option_c,option_d,answer\nSuraj poorab se ugta hai.,Suraj kahan se ugta hai?,Poorab,Paschim,Uttar,Dakshin,A\n"}).json()
    assert len(r["items"]) == 1 and r["items"][0]["roman"]
