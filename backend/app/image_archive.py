"""Stream compressed archives; validate all names/types before restoring any file."""
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
ROOT = Path(os.getenv("IMAGE_DIR", "/app/storage/images"))

def main():
    action = sys.argv[1]
    if action == "backup":
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
            archive.add(ROOT, arcname="images", recursive=False)
            for path in sorted(ROOT.iterdir()):
                if path.name.startswith((".probe-", ".write-check-")) or path.suffix == ".restore":
                    continue  # Temporary probes/staging files are never database photo references.
                if path.is_symlink() or not path.is_file() or not re.fullmatch(r"[0-9a-f]{32}\.jpg", path.name):
                    raise ValueError("Unexpected image directory entry; inspect before backup: " + path.name)
                archive.add(path, arcname="images/" + path.name, recursive=False)
        return
    with tempfile.TemporaryFile() as spool:
        shutil.copyfileobj(sys.stdin.buffer, spool)
        spool.seek(0)
        with tarfile.open(fileobj=spool, mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                if member.name == "images" and member.isdir():
                    continue
                if not member.isfile() or not re.fullmatch(r"images/[0-9a-f]{32}\.jpg", member.name):
                    raise ValueError("Unsafe archive member: " + member.name)
            if action == "validate":
                return
            if action != "restore":
                raise ValueError("Unknown operation")
            ROOT.mkdir(parents=True, exist_ok=True)
            for member in members:
                if not member.isfile():
                    continue
                target = ROOT / Path(member.name).name
                if target.exists():
                    import hashlib
                    with archive.extractfile(member) as source:
                        incoming = hashlib.file_digest(source, "sha256").digest()
                    with target.open("rb") as existing:
                        if hashlib.file_digest(existing, "sha256").digest() != incoming:
                            raise ValueError("Existing immutable image differs: " + target.name)
                    continue
                temporary = target.with_suffix(".restore")
                with archive.extractfile(member) as source, temporary.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
                    dest.flush()
                    os.fsync(dest.fileno())
                os.chmod(temporary, 0o644)
                os.chown(temporary, 10001, 10001)
                os.replace(temporary, target)
if __name__ == "__main__":
    main()
