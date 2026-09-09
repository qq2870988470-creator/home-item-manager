"""Executed by the backend Python runtime through stdin; no host Python needed."""
import hashlib
import io
import json
import sys
import uuid
import urllib.request
import urllib.parse
from PIL import Image
BASE = "http://frontend"
def request(path, body=None, method=None, content_type="application/json"):
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=15) as response:
        value = response.read()
        return json.loads(value) if response.headers.get_content_type() == "application/json" else value
if sys.argv[1] == "create":
    name = "持久化自检-" + uuid.uuid4().hex[:8]
    location = request('/api/locations', {"name": name})
    item = request('/api/items', {"name": name, "location_id": location['id']})
    image = io.BytesIO(); Image.new('RGB', (24, 24), 'blue').save(image, 'PNG')
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="test.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
            + image.getvalue() + f'\r\n--{boundary}--\r\n'.encode())
    photo = request(f"/api/items/{item['id']}/photos", body, content_type='multipart/form-data; boundary='+boundary)
    destination = request('/api/locations', {"name": name+'-抽屉', "parent_id":location['id']})
    request(f"/api/items/{item['id']}/move", {"to_location_id":destination['id'], "note":"持久化测试"})
    digest = hashlib.sha256(request(photo['url'])).hexdigest()
    print(item['id'], photo['url'], digest)
elif sys.argv[1] == "verify":
    item_id, photo_url, expected = sys.argv[2:]
    item = request('/api/items/'+item_id)
    assert item['photos'][0]['url'] == photo_url
    assert hashlib.sha256(request(photo_url)).hexdigest() == expected
    assert len(request('/api/items/'+item_id+'/history')) == 2
    assert request('/api/search?q='+urllib.parse.quote(item['name']))[0]['id'] == int(item_id)
    assert request('/api/health')['postgres'] is True
    print('物品、图片内容、位置历史和搜索验证通过')
