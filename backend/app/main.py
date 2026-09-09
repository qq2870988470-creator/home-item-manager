import io
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from redis import Redis
from sqlalchemy import select, update, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from .db import engine, get_db
from .models import Home, Location, Item, Category, Photo, History
from .schemas import ItemInput, LocationInput, MoveInput

log = logging.getLogger(__name__)
HOME = 1  # V1 is a single trusted household; no public registration.
IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "/app/storage/images"))
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = 20_000_000
cache = Redis(host=os.getenv("REDIS_HOST", "redis"), port=int(os.getenv("REDIS_PORT", "6379")), password=os.getenv("REDIS_PASSWORD"),
              decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
TTL = max(1, min(int(os.getenv("CACHE_TTL", "600")), 600))

@asynccontextmanager
async def lifespan(app):
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    try:
        cache.ping()
    except Exception:
        log.warning("Redis unavailable; continuing without cache")
    probe = IMAGE_DIR / (".probe-" + uuid.uuid4().hex)
    probe.write_bytes(b"ok")
    probe.unlink()
    yield
    cache.close()
    engine.dispose()

app = FastAPI(title="家庭物品位置管理系统", root_path=os.getenv("ROOT_PATH", ""), lifespan=lifespan)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")

@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(status_code=409, content={"detail": "记录仍被引用，或数据冲突；请刷新后重试"})

def row(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def get(db, cls, id, lock=False):
    stmt = select(cls).where(cls.id == id)
    if hasattr(cls, "home_id"):
        stmt = stmt.where(cls.home_id == HOME)
    if lock:
        stmt = stmt.with_for_update()
    result = db.scalar(stmt)
    if result is None:
        raise HTTPException(404, "记录不存在")
    return result

def write_lock(db):
    # Serializes household mutations, including concurrent tree reparenting.
    db.execute(select(Home).where(Home.id == HOME).with_for_update()).scalar_one()

def commit(db):
    # Version changes atomically with data. Redis outages cannot resurrect stale keys.
    db.execute(update(Home).where(Home.id == HOME).values(cache_version=Home.cache_version + 1))
    db.commit()

def cached(db, namespace, suffix, compute):
    version = db.scalar(select(Home.cache_version).where(Home.id == HOME))
    key = f"home:{HOME}:v{version}:{namespace}:{suffix}"
    try:
        value = cache.get(key)
        if value is not None:
            return json.loads(value)
    except Exception:
        pass
    value = jsonable_encoder(compute())
    try:
        cache.setex(key, TTL, json.dumps(value, ensure_ascii=False))
    except Exception:
        pass
    return value

def item_data(db, item):
    result = row(item)
    result["photos"] = [row(p) for p in db.scalars(select(Photo).where(Photo.item_id == item.id).order_by(Photo.id))]
    return result

def validate_item(db, data):
    get(db, Location, data.location_id)
    if data.category_id is not None:
        get(db, Category, data.category_id)

def record_move(db, item, destination, note):
    get(db, Location, destination)
    if item.location_id != destination:
        db.add(History(item_id=item.id, from_location_id=item.location_id,
                       to_location_id=destination, note=note))
        item.location_id = destination
        item.last_confirmed_at = datetime.now(timezone.utc)

@app.get("/health")
def health():
    postgres_ok = redis_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        postgres_ok = False
    try:
        cache.ping()
    except Exception:
        redis_ok = False
    # Redis degradation is visible but does not disable the application.
    return JSONResponse(status_code=200 if postgres_ok else 503, content={
        "status": "ok" if postgres_ok and redis_ok else "degraded",
        "postgres": postgres_ok, "redis": redis_ok})

@app.get("/items")
def items(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: DBSession = Depends(get_db)):
    return [item_data(db, i) for i in db.scalars(select(Item).where(Item.home_id == HOME).order_by(Item.id.desc()).offset(offset).limit(limit))]

@app.get("/items/{id}")
def item(id: int, db: DBSession = Depends(get_db)):
    return item_data(db, get(db, Item, id))

@app.post("/items", status_code=201)
def create_item(data: ItemInput, db: DBSession = Depends(get_db)):
    write_lock(db)
    validate_item(db, data)
    item = Item(home_id=HOME, **data.model_dump())
    db.add(item)
    db.flush()
    db.add(History(item_id=item.id, from_location_id=None, to_location_id=item.location_id, note="首次登记"))
    commit(db)
    return item_data(db, item)

@app.put("/items/{id}")
def edit_item(id: int, data: ItemInput, db: DBSession = Depends(get_db)):
    write_lock(db)
    item = get(db, Item, id, True)
    validate_item(db, data)
    for k, v in data.model_dump(exclude={"location_id"}).items():
        setattr(item, k, v)
    record_move(db, item, data.location_id, "编辑物品时修改位置")
    commit(db)
    return item_data(db, item)

@app.delete("/items/{id}", status_code=204)
def delete_item(id: int, db: DBSession = Depends(get_db)):
    write_lock(db)
    db.delete(get(db, Item, id, True))
    commit(db)
    # Keep original files as recoverable orphans. Never unlink before DB commit.

@app.post("/items/{id}/move")
def move_item(id: int, data: MoveInput, db: DBSession = Depends(get_db)):
    write_lock(db)
    item = get(db, Item, id, True)
    record_move(db, item, data.to_location_id, data.note)
    commit(db)
    return item_data(db, item)

@app.get("/items/{id}/history")
def history(id: int, db: DBSession = Depends(get_db)):
    get(db, Item, id)
    return [row(h) for h in db.scalars(select(History).where(History.item_id == id).order_by(History.moved_at.desc(), History.id.desc()))]

@app.get("/locations")
def locations(db: DBSession = Depends(get_db)):
    return [row(x) for x in db.scalars(select(Location).where(Location.home_id == HOME).order_by(Location.id))]

@app.get("/locations/tree")
def tree(db: DBSession = Depends(get_db)):
    def build():
        nodes = {x["id"]: {**x, "children": []} for x in locations(db)}
        roots = []
        for node in nodes.values():
            if node["parent_id"] in nodes:
                nodes[node["parent_id"]]["children"].append(node)
            else:
                roots.append(node)
        return roots
    return cached(db, "tree", "all", build)

def validate_parent(db, parent, id=None):
    seen = {id} if id else set()
    while parent is not None:
        if parent in seen:
            raise HTTPException(409, "不能将位置移到自身或其子位置下")
        seen.add(parent)
        if len(seen) > 50:
            raise HTTPException(422, "位置层级过深")
        parent = get(db, Location, parent).parent_id

@app.post("/locations", status_code=201)
def create_location(data: LocationInput, db: DBSession = Depends(get_db)):
    write_lock(db)
    validate_parent(db, data.parent_id)
    location = Location(home_id=HOME, **data.model_dump())
    db.add(location)
    commit(db)
    return row(location)

@app.put("/locations/{id}")
def edit_location(id: int, data: LocationInput, db: DBSession = Depends(get_db)):
    write_lock(db)
    location = get(db, Location, id)
    validate_parent(db, data.parent_id, id)
    for k, v in data.model_dump().items():
        setattr(location, k, v)
    commit(db)
    return row(location)

@app.delete("/locations/{id}", status_code=204)
def delete_location(id: int, db: DBSession = Depends(get_db)):
    write_lock(db)
    location = get(db, Location, id)
    if (db.scalar(select(Location.id).where(Location.parent_id == id).limit(1)) or
        db.scalar(select(Item.id).where(Item.location_id == id).limit(1)) or
        db.scalar(select(History.id).where(or_(History.from_location_id == id, History.to_location_id == id)).limit(1))):
        raise HTTPException(409, "位置含子位置、物品或历史引用，不能删除；可以重命名")
    db.delete(location)
    commit(db)

@app.get("/search")
def search(q: str = Query(..., min_length=1, max_length=200), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: DBSession = Depends(get_db)):
    q = q.strip()
    if not q:
        raise HTTPException(422, "请输入搜索内容")
    def find():
        stmt = select(Item).join(Location, Item.location_id == Location.id).where(Item.home_id == HOME,
            or_(Item.name.icontains(q, autoescape=True), Item.description.icontains(q, autoescape=True), Location.name.icontains(q, autoescape=True)))
        return [item_data(db, i) for i in db.scalars(stmt.order_by(Item.id.desc()).offset(offset).limit(limit))]
    return cached(db, "search", f"{q}:{offset}:{limit}", find)

@app.get("/categories")
def categories(db: DBSession = Depends(get_db)):
    return [row(x) for x in db.scalars(select(Category).where(Category.home_id == HOME))]

@app.post("/items/{id}/photos", status_code=201)
def upload_photo(id: int, file: UploadFile = File(...), db: DBSession = Depends(get_db)):
    raw = file.file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "照片不得超过 10 MB")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError()
            source.load()
            clean = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "请上传有效的 JPG、PNG 或 WebP 图片")
    write_lock(db)
    get(db, Item, id, True)
    filename = uuid.uuid4().hex + ".jpg"
    path = IMAGE_DIR / filename
    try:
        # Re-encoding removes metadata and disallows executable/SVG content.
        with path.open("xb") as out:
            clean.save(out, "JPEG", quality=90)
            out.flush()
            os.fsync(out.fileno())
        cover = db.scalar(select(Photo.id).where(Photo.item_id == id).limit(1)) is None
        photo = Photo(item_id=id, url="/images/" + filename, is_cover=cover)
        db.add(photo)
        commit(db)
    except Exception:
        db.rollback()
        # Preserve file on uncertain commit; an orphan is safer than a missing photo.
        raise
    return row(photo)
