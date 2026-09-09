"""Fast contract tests use ephemeral SQLite; PostgreSQL acceptance is separate."""
import io
import os
import sys
from pathlib import Path
import pytest
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("IMAGE_DIR", "/tmp/home-item-test-images")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from PIL import Image
from app import main
from app.db import get_db
from app.models import Base, User, Home, Location

class Cache:
    def __init__(self): self.data = {}; self.fail = False
    def get(self, key):
        if self.fail: raise ConnectionError()
        return self.data.get(key)
    def setex(self, key, ttl, value):
        assert 0 < ttl <= 600
        if self.fail: raise ConnectionError()
        self.data[key] = value
    def ping(self):
        if self.fail: raise ConnectionError()
        return True

@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def configure(conn, record): conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as db:
        db.add(User(id=1, name="test")); db.commit()
        db.add(Home(id=1, name="家", owner_id=1)); db.commit()
        db.add(Location(id=1, home_id=1, name="书房", type="room")); db.commit()
    def dependency():
        with sessions() as db: yield db
    main.app.dependency_overrides[get_db] = dependency
    monkeypatch.setattr(main, "cache", Cache())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "IMAGE_DIR", tmp_path)
    # Do not start production lifespan; external services are exercised in acceptance.
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    engine.dispose()

def add(client, name="剪刀"):
    response = client.post("/items", json={"name":name, "location_id":1})
    assert response.status_code == 201, response.text
    return response.json()

def test_move_and_put_both_keep_history(client):
    item=add(client)
    loc=client.post("/locations", json={"name":"抽屉","parent_id":1}).json()
    assert client.post(f"/items/{item['id']}/move",json={"to_location_id":loc['id'],"note":"整理"}).status_code==200
    assert client.put(f"/items/{item['id']}",json={"name":"剪刀","location_id":1}).status_code==200
    history=client.get(f"/items/{item['id']}/history").json()
    assert len(history)==3
    assert history[0]['from_location_id']==loc['id'] and history[0]['to_location_id']==1

def test_invalid_move_is_atomic(client):
    item=add(client)
    assert client.post(f"/items/{item['id']}/move",json={"to_location_id":999}).status_code==404
    assert len(client.get(f"/items/{item['id']}/history").json())==1

def test_tree_rejects_cycle_and_referenced_delete(client):
    loc=client.post('/locations',json={"name":"抽屉","parent_id":1}).json()
    assert client.put('/locations/1',json={"name":"书房","parent_id":loc['id']}).status_code==409
    assert client.delete('/locations/1').status_code==409
    assert client.get('/locations/tree').json()[0]['children'][0]['id']==loc['id']

def test_history_prevents_location_deletion(client):
    item=add(client)
    loc=client.post('/locations',json={"name":"柜子"}).json()
    client.post(f"/items/{item['id']}/move",json={"to_location_id":loc['id']})
    assert client.delete('/locations/1').status_code==409

def test_cache_recovers_without_stale_results(client):
    assert client.get('/search?q=剪刀').json()==[]
    main.cache.fail=True
    item=add(client)
    main.cache.fail=False
    assert len(client.get('/search?q=剪刀').json())==1
    client.delete(f"/items/{item['id']}")
    assert client.get('/search?q=剪刀').json()==[]

def test_cache_tree_invalidation(client):
    assert client.get('/locations/tree').json()[0]['name']=='书房'
    client.put('/locations/1',json={"name":"新书房"})
    assert client.get('/locations/tree').json()[0]['name']=='新书房'

def test_upload_validation_and_cover(client):
    item=add(client); endpoint=f"/items/{item['id']}/photos"
    assert client.post(endpoint,files={"file":('fake.jpg',b'not an image','image/jpeg')}).status_code==422
    stream=io.BytesIO(); Image.new('RGB',(8,8),'blue').save(stream,'PNG')
    first=client.post(endpoint,files={"file":('a.png',stream.getvalue(),'image/png')})
    assert first.status_code==201,first.text
    assert first.json()['is_cover'] is True
    assert (main.IMAGE_DIR/Path(first.json()['url']).name).exists()
    second=client.post(endpoint,files={"file":('b.png',stream.getvalue(),'image/png')})
    assert second.json()['is_cover'] is False
    assert len(client.get(f"/items/{item['id']}").json()['photos'])==2

def test_validation_and_literal_search(client):
    assert client.post('/items',json={"name":" ","location_id":1}).status_code==422
    assert client.post('/items',json={"name":"x","location_id":1,"quantity":0}).status_code==422
    add(client,'100% 棉被'); add(client,'普通棉被')
    assert len(client.get('/search',params={'q':'%'}).json())==1
    assert client.get('/search?q=%20').status_code==422

def test_redis_degrades_without_stopping_api(client):
    main.cache.fail=True
    assert client.get('/health').json()['status']=='degraded'
    assert client.get('/health').status_code==200
    add(client)

def test_item_delete_cascades_records_keeps_file(client):
    item=add(client)
    stream=io.BytesIO(); Image.new('RGB',(8,8)).save(stream,'PNG')
    photo=client.post(f"/items/{item['id']}/photos",files={"file":('a.png',stream.getvalue())}).json()
    assert client.delete(f"/items/{item['id']}").status_code==204
    assert client.get(f"/items/{item['id']}").status_code==404
    assert (main.IMAGE_DIR/Path(photo['url']).name).exists()
