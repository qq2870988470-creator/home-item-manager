import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import pytest
ROOT = Path(__file__).resolve().parents[1]

def archive(name, link=False):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:gz') as tar:
        entry=tarfile.TarInfo(name)
        if link:
            entry.type=tarfile.SYMTYPE;entry.linkname='/etc/passwd';tar.addfile(entry)
        else:
            entry.size=3;tar.addfile(entry,io.BytesIO(b'abc'))
    return output.getvalue()

@pytest.mark.parametrize('name,link',[('../escape.jpg',False),('images/evil.jpg',False),('images/'+'a'*32+'.jpg',True),('/etc/passwd',False)])
def test_archive_rejects_unsafe_members(name,link,tmp_path):
    env={**os.environ,'IMAGE_DIR':str(tmp_path),'PYTHONPATH':str(ROOT/'backend')}
    result=subprocess.run([sys.executable,'-m','app.image_archive','validate'],input=archive(name,link),capture_output=True,env=env)
    assert result.returncode!=0
    assert not list(tmp_path.iterdir())

def test_archive_accepts_valid_uuid(tmp_path):
    env={**os.environ,'IMAGE_DIR':str(tmp_path),'PYTHONPATH':str(ROOT/'backend')}
    result=subprocess.run([sys.executable,'-m','app.image_archive','validate'],input=archive('images/'+'a'*32+'.jpg'),capture_output=True,env=env)
    assert result.returncode==0,result.stderr
