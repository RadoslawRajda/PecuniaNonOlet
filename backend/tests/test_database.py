import os
from contextlib import closing

import pytest
from app.database import connect_db


def test_database_file_is_private_on_posix(tmp_path, monkeypatch):
    path = tmp_path / "private" / "pecunia.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    with closing(connect_db()) as db, db:
        db.execute("CREATE TABLE probe(value TEXT)")

    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_database_path_rejects_symlinks(tmp_path, monkeypatch):
    target = tmp_path / "target.db"
    target.touch()
    link = tmp_path / "linked.db"
    link.symlink_to(target)
    monkeypatch.setenv("DATABASE_PATH", str(link))

    with pytest.raises(ValueError, match="symbolic link"):
        connect_db()
