# app/database.py -- local SQLite index of the FX library.
#
# Eagle-style standalone library: catalogs local .uasset files on disk.
# Each row is a real file (source_path). Thumbnails and (optionally) copies of
# the files live under the library directory. UE is NOT required to populate
# this -- it only acts as an optional thumbnail renderer.

import os
import json
import sqlite3
from typing import List, Optional

from app.models import FXAsset, FxPackEntry


SCHEMA = """
CREATE TABLE IF NOT EXISTS fx_assets (
    source_path  TEXT PRIMARY KEY,
    name         TEXT,
    type         TEXT,
    class_name   TEXT,
    stored_path  TEXT,
    thumb_path   TEXT,
    tags         TEXT,
    favorite     INTEGER DEFAULT 0,
    rating       INTEGER DEFAULT 0,
    note         TEXT,
    size         INTEGER,
    imported_at  TEXT,
    source       TEXT,
    project_path TEXT,
    health       TEXT,
    tier         INTEGER,
    deps         TEXT,
    blueprint    INTEGER DEFAULT 0,
    deleted      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fxpacks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT,
    fxpack_path   TEXT UNIQUE,
    source_project TEXT,
    engine_version TEXT,
    manifest      TEXT,
    added_at      TEXT
);
CREATE TABLE IF NOT EXISTS folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id   INTEGER REFERENCES folders(id),
    name        TEXT NOT NULL,
    path        TEXT,
    virtual     INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS folder_assets (
    folder_id   INTEGER REFERENCES folders(id),
    source_path TEXT REFERENCES fx_assets(source_path),
    PRIMARY KEY (folder_id, source_path)
);
CREATE TABLE IF NOT EXISTS smart_folders (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    query   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_folder_assets ON folder_assets(folder_id);
"""


class Database:
    def __init__(self, path, backup: bool = True):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path)
        # (5) Durability: WAL gives better crash-resilience and concurrent
        # reads vs the default rollback journal; NORMAL sync is safe with WAL.
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        if backup:
            # Snapshot the DB as found at startup (before we write this
            # session). Checkpoint first so the main file holds committed data.
            try:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._snapshot_backup(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()

    def _snapshot_backup(self, path):
        """Keep a single rolling .bak of the library as it was at launch."""
        try:
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                return
            bak = path + ".bak"
            import shutil
            shutil.copy2(path, bak)
        except Exception:
            pass

    def _migrate(self):
        """One-time migration from the legacy schema (object_path PK) to the
        standalone schema (source_path PK). Preserves existing rows, and adds
        any missing columns (e.g. blueprint) so older libraries keep working."""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(fx_assets)")]
        if "source_path" not in cols:
            # Legacy table used object_path as primary key; rename and rebuild.
            try:
                old = self.conn.execute(
                    "SELECT object_path,name,type,class_name,stored_path,thumb_path,tags,"
                    "favorite,rating,note,size,imported_at,source,project_path,health,tier,deps "
                    "FROM fx_assets").fetchall()
            except Exception:
                old = []
            self.conn.execute("ALTER TABLE fx_assets RENAME TO fx_assets_old")
            self.conn.executescript(SCHEMA)
            for r in old:
                self.conn.execute(
                    "INSERT INTO fx_assets "
                    "(source_path,name,type,class_name,stored_path,thumb_path,tags,"
                    "favorite,rating,note,size,imported_at,source,project_path,health,tier,deps) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r[0], r[1], r[2] or "Unknown", r[3] or "", r[4], r[5], r[6] or "",
                     r[7], r[8] or 0, r[9] or "", r[10] or 0, r[11] or "",
                     r[12] or "scan", r[13] or "", r[14] or "ok", r[15] or 1, r[16] or "[]"))
            try:
                self.conn.execute("DROP TABLE fx_assets_old")
            except Exception:
                pass
            self.conn.commit()

        # Add the blueprint column if it is missing from an older standalone DB.
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(fx_assets)")]
        if "blueprint" not in cols:
            try:
                self.conn.execute(
                    "ALTER TABLE fx_assets ADD COLUMN blueprint INTEGER DEFAULT 0")
                self.conn.commit()
            except Exception:
                pass

        # Add the deleted column if missing.
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(fx_assets)")]
        if "deleted" not in cols:
            try:
                self.conn.execute(
                    "ALTER TABLE fx_assets ADD COLUMN deleted INTEGER DEFAULT 0")
                self.conn.commit()
            except Exception:
                pass

        # Add the has_thumb column if missing. has_thumb = 1 means a REAL
        # embedded thumbnail was extracted (as opposed to a generated
        # placeholder). Old rows have no flag yet, so backfill it by
        # re-deriving from the on-disk .uasset (one-time, idempotent:
        # only rows with has_thumb = 0 are touched, so it never runs again).
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(fx_assets)")]
        if "has_thumb" not in cols:
            try:
                self.conn.execute(
                    "ALTER TABLE fx_assets ADD COLUMN has_thumb INTEGER DEFAULT 0")
                self.conn.commit()
            except Exception:
                pass
            try:
                import os as _os
                import tempfile
                from app import uasset_thumb as _ut
                for sp, in self.conn.execute(
                        "SELECT source_path FROM fx_assets "
                        "WHERE has_thumb IS NULL OR has_thumb = 0").fetchall():
                    if not sp or not _os.path.exists(sp):
                        continue
                    tmp = _os.path.join(
                        tempfile.gettempdir(),
                        "fx_thumb_chk_%s.png" % _os.path.basename(sp))
                    try:
                        has = 1 if _ut.extract_thumbnail(sp, tmp) else 0
                    except Exception:
                        has = 0
                    try:
                        _os.remove(tmp)
                    except Exception:
                        pass
                    self.conn.execute(
                        "UPDATE fx_assets SET has_thumb=? WHERE source_path=?",
                        (has, sp))
                self.conn.commit()
            except Exception:
                # Backfill is best-effort; the column defaults to 0 either way.
                pass

        # Self-healing repair (RUNS ONCE). A previous scanner build defaulted
        # `tier` to 1 on every scan and could clear `has_thumb` on a transient
        # re-scan failure, leaving rows with `tier=1 AND has_thumb=0` -- i.e.
        # dirty "looks-has-image-but-flagged-none" records. Re-derive the real
        # state from the on-disk .uasset for every still-unconfirmed row, so the
        # "has thumbnail" filter is accurate. Gated by a meta flag so it only
        # does this work once (idempotent thereafter).
        try:
            _flag = self.conn.execute(
                "SELECT value FROM meta WHERE key='repair_hasthumb_v1'"
            ).fetchone()
            if _flag is None:
                import os as _os
                import tempfile
                from app import uasset_thumb as _ut
                for sp, in self.conn.execute(
                        "SELECT source_path FROM fx_assets "
                        "WHERE has_thumb IS NULL OR has_thumb = 0").fetchall():
                    if not sp:
                        continue
                    if _os.path.exists(sp):
                        tmp = _os.path.join(
                            tempfile.gettempdir(),
                            "fx_thumb_rep_%s.png" % _os.path.basename(sp))
                        try:
                            ok = bool(_ut.extract_thumbnail(sp, tmp))
                        except Exception:
                            ok = False
                        try:
                            _os.remove(tmp)
                        except Exception:
                            pass
                        # Real embedded image -> tier 1; placeholder -> tier 4.
                        self.conn.execute(
                            "UPDATE fx_assets SET has_thumb=?, tier=? "
                            "WHERE source_path=?",
                            (1 if ok else 0, 1 if ok else 4, sp))
                    else:
                        # Source unreachable: cannot confirm a real image, so
                        # treat as placeholder-only (tier 4) and keep flag 0.
                        self.conn.execute(
                            "UPDATE fx_assets SET tier=4 "
                            "WHERE source_path=? AND (has_thumb IS NULL "
                            "OR has_thumb = 0)",
                            (sp,))
                self.conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) "
                    "VALUES ('repair_hasthumb_v1', '1')")
                self.conn.commit()
        except Exception:
            # Repair is best-effort; never block app startup on it.
            pass

    # ---------- write ----------
    def upsert_asset(self, a: FXAsset):
        # Merge user-owned fields so a re-scan never wipes labels/stars/notes.
        prev = self.get_asset(a.source_path)
        if prev is not None:
            tags = a.tags if a.tags else prev.tags
            favorite = a.favorite if a.favorite else prev.favorite
            rating = a.rating if a.rating else prev.rating
            note = a.note if a.note else prev.note
            deleted = a.deleted if a.deleted else prev.deleted
        else:
            tags, favorite, rating, note, deleted = (
                a.tags, a.favorite, a.rating, a.note, a.deleted)
        deps = json.dumps(a.deps, ensure_ascii=False)
        self.conn.execute(
            "INSERT OR REPLACE INTO fx_assets "
            "(source_path,name,type,class_name,stored_path,thumb_path,tags,"
            "favorite,rating,note,size,imported_at,source,project_path,health,tier,deps,blueprint,deleted,has_thumb) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.source_path, a.name, a.type, a.class_name, a.stored_path,
             a.thumb_path, tags, int(favorite), rating, note, a.size,
             a.imported_at, a.source, a.project_path, a.health, a.tier, deps,
             int(a.blueprint), int(deleted),
             int(getattr(a, "has_thumb", False))))
        self.conn.commit()

    def upsert_assets(self, assets: List[FXAsset]):
        for a in assets:
            self.upsert_asset(a)

    def set_thumb(self, source_path, thumb_path):
        self.conn.execute("UPDATE fx_assets SET thumb_path=? WHERE source_path=?",
                          (thumb_path, source_path))
        self.conn.commit()

    def set_has_thumb(self, source_path, has: bool):
        """Flag whether a REAL embedded/manual thumbnail exists (as opposed to
        a generated placeholder). Drives the 'has thumbnail' / 'no thumbnail'
        sidebar filters."""
        self.conn.execute("UPDATE fx_assets SET has_thumb=? WHERE source_path=?",
                          (1 if has else 0, source_path))
        self.conn.commit()

    def set_tier(self, source_path, tier: int):
        """Mark how a thumbnail was produced (1=engine static, 2=playing/peak,
        3=manual). Used to badge cards and to distinguish real playing frames."""
        self.conn.execute("UPDATE fx_assets SET tier=? WHERE source_path=?",
                          (int(tier), source_path))
        self.conn.commit()

    def set_tags(self, source_path, tags):
        self.conn.execute("UPDATE fx_assets SET tags=? WHERE source_path=?",
                          (tags, source_path))
        self.conn.commit()

    def set_favorite(self, source_path, fav: bool):
        self.conn.execute("UPDATE fx_assets SET favorite=? WHERE source_path=?",
                          (int(fav), source_path))
        self.conn.commit()

    def set_rating(self, source_path, rating: int):
        self.conn.execute("UPDATE fx_assets SET rating=? WHERE source_path=?",
                          (int(rating), source_path))
        self.conn.commit()

    def set_note(self, source_path, note: str):
        self.conn.execute("UPDATE fx_assets SET note=? WHERE source_path=?",
                          (note, source_path))
        self.conn.commit()

    def set_health(self, source_path, health: str):
        self.conn.execute("UPDATE fx_assets SET health=? WHERE source_path=?",
                         (health, source_path))
        self.conn.commit()

    def rename_asset(self, source_path, name: str):
        """Rename the display name of an asset (the on-disk file is untouched)."""
        name = (name or "").strip()
        if not name:
            return
        self.conn.execute("UPDATE fx_assets SET name=? WHERE source_path=?",
                         (name, source_path))
        self.conn.commit()

    def delete_asset(self, source_path):
        """Soft-delete: mark as deleted (moved to trash)."""
        self.conn.execute("UPDATE fx_assets SET deleted=1 WHERE source_path=?",
                          (source_path,))
        self.conn.commit()

    def restore_asset(self, source_path):
        """Restore a soft-deleted asset from trash."""
        self.conn.execute("UPDATE fx_assets SET deleted=0 WHERE source_path=?",
                          (source_path,))
        self.conn.commit()

    def permanently_delete_asset(self, source_path):
        """Permanently remove an asset from the database."""
        self.conn.execute("DELETE FROM fx_assets WHERE source_path=?",
                          (source_path,))
        self.conn.commit()

    def empty_trash(self):
        """Permanently delete all soft-deleted assets."""
        self.conn.execute("DELETE FROM fx_assets WHERE deleted=1")
        self.conn.commit()

    # ---------- read ----------
    def get_assets(self, type=None, fav_only=False, tag=None, q=None,
                   blueprint=None, include_deleted=False) -> List[FXAsset]:
        sql = ("SELECT source_path,name,type,class_name,stored_path,thumb_path,tags,"
               "favorite,rating,note,size,imported_at,source,project_path,health,tier,deps,blueprint,deleted,has_thumb "
               "FROM fx_assets WHERE 1=1")
        args = []
        if not include_deleted:
            sql += " AND deleted=0"
        if type and type not in ("all", "All", ""):
            sql += " AND type=?"
            args.append(type)
        if fav_only:
            sql += " AND favorite=1"
        if tag:
            sql += " AND tags LIKE ?"
            args.append("%" + tag + "%")
        if q:
            q = "%" + q + "%"
            sql += " AND (name LIKE ? OR tags LIKE ? OR source_path LIKE ?)"
            args += [q, q, q]
        if blueprint is not None:
            sql += " AND blueprint=?"
            args.append(1 if blueprint else 0)
        sql += " ORDER BY name COLLATE NOCASE"
        return self._rows_to_assets(self.conn.execute(sql, args).fetchall())

    def get_trash(self) -> List[FXAsset]:
        """Return all soft-deleted assets."""
        cur = self.conn.execute(
            "SELECT source_path,name,type,class_name,stored_path,thumb_path,tags,"
            "favorite,rating,note,size,imported_at,source,project_path,health,tier,deps,blueprint,deleted,has_thumb "
            "FROM fx_assets WHERE deleted=1 ORDER BY name COLLATE NOCASE")
        return self._rows_to_assets(cur.fetchall())

    def get_asset(self, source_path) -> Optional[FXAsset]:
        cur = self.conn.execute(
            "SELECT source_path,name,type,class_name,stored_path,thumb_path,tags,"
            "favorite,rating,note,size,imported_at,source,project_path,health,tier,deps,blueprint,deleted,has_thumb "
            "FROM fx_assets WHERE source_path=?", (source_path,))
        rows = cur.fetchall()
        return self._rows_to_assets(rows)[0] if rows else None

    def all_tags(self) -> List[str]:
        cur = self.conn.execute("SELECT DISTINCT tags FROM fx_assets")
        tags = set()
        for (t,) in cur.fetchall():
            if t:
                for part in t.split(","):
                    part = part.strip()
                    if part:
                        tags.add(part)
        return sorted(tags)

    def all_tags_with_counts(self) -> List[tuple]:
        """Return [(tag, count)] sorted by count desc then name."""
        cur = self.conn.execute(
            "SELECT tags FROM fx_assets WHERE tags IS NOT NULL AND tags != ''")
        counts = {}
        for (t,) in cur.fetchall():
            for part in t.split(","):
                part = part.strip()
                if part:
                    counts[part] = counts.get(part, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    def rename_tag(self, old: str, new: str):
        """Rename a tag everywhere it appears in asset tags."""
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new or old == new:
            return
        cur = self.conn.execute(
            "SELECT source_path, tags FROM fx_assets WHERE tags LIKE ?",
            ("%" + old + "%",))
        for source_path, tags in cur.fetchall():
            parts = [p.strip() for p in (tags or "").split(",") if p.strip()]
            if old not in parts:
                continue
            parts = [p for p in parts if p != old]
            parts.append(new)
            self.set_tags(source_path, ",".join(parts))
        self.conn.commit()

    def delete_tag(self, tag: str):
        """Remove a tag from every asset that uses it."""
        tag = (tag or "").strip()
        if not tag:
            return
        cur = self.conn.execute(
            "SELECT source_path, tags FROM fx_assets WHERE tags LIKE ?",
            ("%" + tag + "%",))
        for source_path, tags in cur.fetchall():
            parts = [p.strip() for p in (tags or "").split(",")
                     if p.strip() and p != tag]
            self.set_tags(source_path, ",".join(parts))
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM fx_assets").fetchone()[0]

    def _rows_to_assets(self, rows) -> List[FXAsset]:
        out = []
        for r in rows:
            deps = json.loads(r[16]) if r[16] else []
            out.append(FXAsset(
                source_path=r[0], name=r[1], type=r[2] or "Unknown",
                class_name=r[3] or "", stored_path=r[4], thumb_path=r[5],
                tags=r[6] or "", favorite=bool(r[7]), rating=r[8] or 0,
                note=r[9] or "", size=r[10] or 0, imported_at=r[11] or "",
                source=r[12] or "scan", project_path=r[13] or "",
                health=r[14] or "ok", tier=r[15] or 1, deps=deps,
                blueprint=bool(r[17]), deleted=bool(r[18]),
                has_thumb=bool(r[19])))
        return out

    # ---------- fxpacks ----------
    def add_fxpack(self, entry: FxPackEntry):
        self.conn.execute(
            "INSERT OR REPLACE INTO fxpacks (name,fxpack_path,source_project,engine_version,manifest,added_at) "
            "VALUES (?,?,?,?,?,?)",
            (entry.name, entry.fxpack_path, entry.source_project, entry.engine_version,
             entry.manifest, entry.added_at))
        self.conn.commit()

    def get_fxpacks(self) -> List[FxPackEntry]:
        cur = self.conn.execute(
            "SELECT name,fxpack_path,source_project,engine_version,manifest,added_at FROM fxpacks")
        return [FxPackEntry(*r) for r in cur.fetchall()]

    # ---------- folders ----------
    def add_folder(self, name, parent_id=None, path=None, virtual=1) -> int:
        from datetime import datetime
        cur = self.conn.execute(
            "INSERT INTO folders (parent_id, name, path, virtual, created_at) VALUES (?,?,?,?,?)",
            (parent_id, name, path, 1 if virtual else 0, datetime.now().isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def get_folders(self):
        """Return all folders as dicts."""
        cur = self.conn.execute(
            "SELECT id, parent_id, name, path, virtual, created_at FROM folders ORDER BY name")
        cols = ["id", "parent_id", "name", "path", "virtual", "created_at"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def rename_folder(self, folder_id, name):
        self.conn.execute("UPDATE folders SET name=? WHERE id=?", (name, folder_id))
        self.conn.commit()

    def delete_folder(self, folder_id):
        """Delete a folder and its asset associations (children are kept, parent_id becomes NULL)."""
        self.conn.execute("DELETE FROM folder_assets WHERE folder_id=?", (folder_id,))
        self.conn.execute("UPDATE folders SET parent_id=NULL WHERE parent_id=?", (folder_id,))
        self.conn.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        self.conn.commit()

    def add_asset_to_folder(self, source_path, folder_id):
        self.conn.execute(
            "INSERT OR IGNORE INTO folder_assets (folder_id, source_path) VALUES (?,?)",
            (folder_id, source_path))
        self.conn.commit()

    def remove_asset_from_folder(self, source_path, folder_id):
        self.conn.execute(
            "DELETE FROM folder_assets WHERE folder_id=? AND source_path=?",
            (folder_id, source_path))
        self.conn.commit()

    def get_folder_assets(self, folder_id):
        """Return source_paths of assets directly in this folder."""
        cur = self.conn.execute(
            "SELECT source_path FROM folder_assets WHERE folder_id=?", (folder_id,))
        return [r[0] for r in cur.fetchall()]

    def get_asset_folders(self, source_path):
        """Return folder_ids that contain this asset."""
        cur = self.conn.execute(
            "SELECT folder_id FROM folder_assets WHERE source_path=?", (source_path,))
        return [r[0] for r in cur.fetchall()]

    # ---------- smart folders (saved searches) ----------
    def create_smart_folder(self, name: str, query: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO smart_folders (name, query) VALUES (?, ?)",
            (name, json.dumps(query, ensure_ascii=False)))
        self.conn.commit()
        return cur.lastrowid

    def get_smart_folders(self):
        """Return saved smart folders as dicts with parsed query."""
        cur = self.conn.execute(
            "SELECT id, name, query FROM smart_folders ORDER BY name COLLATE NOCASE")
        out = []
        for fid, name, query in cur.fetchall():
            try:
                q = json.loads(query) if query else {}
            except Exception:
                q = {}
            out.append({"id": fid, "name": name, "query": q})
        return out

    def rename_smart_folder(self, folder_id, name):
        self.conn.execute("UPDATE smart_folders SET name=? WHERE id=?",
                          (name, folder_id))
        self.conn.commit()

    def delete_smart_folder(self, folder_id):
        self.conn.execute("DELETE FROM smart_folders WHERE id=?", (folder_id,))
        self.conn.commit()
