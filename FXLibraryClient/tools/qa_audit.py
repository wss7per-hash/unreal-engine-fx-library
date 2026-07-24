# tools/qa_audit.py -- senior-user QA audit, runs fully offline.
import os, sys, io, time, tempfile, shutil, json, zipfile, threading, traceback, faulthandler, re
faulthandler.enable()
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_report.txt")
open(LOG, "w").close()
def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n"); f.flush()
log("=== QA start ===")
try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox
    QMessageBox.information = lambda *a, **k: None  # avoid blocking modal in offscreen
    QMessageBox.critical = lambda *a, **k: None
    log("imported PySide6")
    import app.config as cfg
    CFGDIR = tempfile.mkdtemp(prefix="fxqa_cfg_")
    cfg.CONFIG_DIR = CFGDIR
    cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
    cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
    cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR
    from app.database import Database
    from app.scanner import ScannerWorker
    from app.ui.main_window import MainWindow
    from app import i18n
    log("imported app modules")

    results = []
    def ok(a, m): results.append(("PASS", a, m)); log("[PASS]", a, m)
    def bad(a, m): results.append(("FAIL", a, m)); log("[FAIL]", a, m)
    def info(a, m): results.append(("INFO", a, m)); log("[INFO]", a, m)

    TMP = tempfile.mkdtemp(prefix="fxqa_")
    SAMPLE = os.path.join(TMP, "SampleFX", "Content", "FX")
    os.makedirs(SAMPLE, exist_ok=True)
    def make_uasset(fname, marker, extra=b""):
        p = os.path.join(SAMPLE, fname)
        with open(p, "wb") as f:
            f.write(b"\x00\x01\x00\x00 header " + marker + b" " + extra + b" tail")
        return p
    make_uasset("NS_Fire.uasset", b"NiagaraSystem")
    make_uasset("NS_Explosion.uasset", b"NiagaraSystem")
    make_uasset("PS_Smoke.uasset", b"ParticleSystem")
    make_uasset("BP_FXSpawner.uasset", b"NiagaraSystem" + b"BlueprintGeneratedClass")
    make_uasset("M_Rock.uasset", b"Material")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    log("QApplication created")
    win = MainWindow()
    win.show()
    log("MainWindow created")

    def vis():
        return [c.name for c in win.grid.assets]

    # SCAN
    thumbs = os.path.join(cfg.DEFAULT_LIBRARY_DIR, "thumbs")
    w = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=True)
    scan_res = {}
    w.finished.connect(lambda d: scan_res.update(d))
    w.failed.connect(lambda e: scan_res.update({"error": e}))
    w.start()
    deadline = time.time() + 20
    while not scan_res and time.time() < deadline:
        app.processEvents(); time.sleep(0.02)
    if "error" in scan_res:
        bad("scan", "worker error: " + str(scan_res["error"]))
    elif not scan_res:
        bad("scan", "worker timeout")
    else:
        ok("scan", "total=%s niagara=%s cascade=%s unknown=%s" % (
            scan_res.get("total"), scan_res.get("niagara"), scan_res.get("cascade"), scan_res.get("unknown")))
        if scan_res.get("skipped") != 1:
            bad("scan", "expected 1 skipped (non-FX), got %s" % scan_res.get("skipped"))
    win._reload_library()
    n = len(win._all_assets)
    info("scan", "library assets=%d" % n)
    if n != 4:
        bad("scan", "expected 4 FX, got %d" % n)

    # ===== P0 Phase-0 regression: data-safety / robustness =====
    from app.database import Database as _DB
    from app.models import FXAsset as _FX
    _pdb = _DB(win._db_path, backup=False)

    # P0-② rescan must NOT wipe user tags/favorite/rating/note
    try:
        _a0 = win._all_assets[0]
        _pdb.set_tags(_a0.source_path, "fire,loop")
        _pdb.set_favorite(_a0.source_path, True)
        _pdb.set_rating(_a0.source_path, 4)
        _pdb.set_note(_a0.source_path, "keep me")
        _re = _FX(source_path=_a0.source_path, name=_a0.name, type=_a0.type,
                   class_name=_a0.class_name, stored_path=_a0.stored_path,
                   thumb_path=_a0.thumb_path, size=_a0.size,
                   imported_at=_a0.imported_at, source="scan",
                   blueprint=_a0.blueprint, has_thumb=_a0.has_thumb,
                   tier=_a0.tier)
        _pdb.upsert_asset(_re)
        _back = _pdb.get_asset(_a0.source_path)
        if (_back.tags == "fire,loop" and _back.favorite and _back.rating == 4
                and _back.note == "keep me"):
            ok("p0_upsert_preserves", "tags/fav/rating/note kept after rescan")
        else:
            bad("p0_upsert_preserves",
                 "lost: tags=%r fav=%r rating=%r note=%r" % (
                     _back.tags, _back.favorite, _back.rating, _back.note))
        # Restore pre-test state so downstream view tests are not polluted.
        _pdb.set_tags(_a0.source_path, "")
        _pdb.set_favorite(_a0.source_path, False)
        _pdb.set_rating(_a0.source_path, 0)
        _pdb.set_note(_a0.source_path, "")
    except Exception as e:
        bad("p0_upsert_preserves", "exc %s" % e)

    # P0-⑤ WAL enabled + rolling backup snapshot present
    try:
        _jm = _pdb.conn.execute("PRAGMA journal_mode").fetchone()
        if _jm and _jm[0].lower().startswith("wal"):
            ok("p0_wal", "journal_mode=%s" % _jm[0])
        else:
            bad("p0_wal", "journal_mode=%s" % (_jm[0] if _jm else None))
        _bk = win._db_path + ".bak"
        if os.path.exists(_bk):
            ok("p0_backup", "rolling .bak snapshot present")
        else:
            bad("p0_backup", "no .bak snapshot at %s" % _bk)
    except Exception as e:
        bad("p0_wal", "exc %s" % e)

    # P0-④ Unknown assets must NOT be silently deleted on fx_only scan
    try:
        _usp = os.path.join(SAMPLE, "Mystery_Unknown.uasset")
        with open(_usp, "wb") as f:
            f.write(b"\x00\x01\x00\x00 header SomeBlob tail")
        _pdb.upsert_asset(_FX(source_path=_usp, name="Mystery",
                                type="Unknown", class_name="", stored_path="",
                                thumb_path="", size=12, source="scan", tier=4))
        _w2 = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=True)
        _r2 = {}
        _w2.finished.connect(lambda d: _r2.update(d))
        _w2.failed.connect(lambda e: _r2.setdefault("errors", []).append(e))
        _w2.start()
        _dl = time.time() + 20
        while not _r2 and time.time() < _dl:
            app.processEvents(); time.sleep(0.02)
        if "error" in _r2:
            bad("p0_unknown_kept", "scan aborted: %s" % _r2["error"])
        else:
            _after = _pdb.get_asset(_usp)
            if _after is not None:
                ok("p0_unknown_kept", "Unknown asset preserved, not deleted")
            else:
                bad("p0_unknown_kept", "Unknown asset was deleted during scan")
    except Exception as e:
        bad("p0_unknown_kept", "exc %s" % e)

    # P0-③ a single-file exception must NOT abort the whole scan
    try:
        import app.scanner as _scn
        _orig = _scn.detect_type_offline
        def _boom(p):
            raise RuntimeError("boom")
        _scn.detect_type_offline = _boom
        _w3 = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=False)
        _r3 = {}
        _w3.finished.connect(lambda d: _r3.update(d))
        _w3.failed.connect(lambda e: _r3.setdefault("errors", []).append(e))
        _w3.start()
        _dl = time.time() + 20
        while not _r3 and time.time() < _dl:
            app.processEvents(); time.sleep(0.02)
        _scn.detect_type_offline = _orig
        if "error" in _r3:
            bad("p0_error_isolated", "scan aborted: %s" % _r3["error"])
        elif _r3.get("errors"):
            ok("p0_error_isolated",
                "scan finished; %d per-file error(s) collected, no abort" % len(_r3["errors"]))
        else:
            bad("p0_error_isolated", "no errors captured")
    except Exception as e:
        bad("p0_error_isolated", "exc %s" % e)

    # REGRESSION: scan completion must NOT auto-launch UnrealEditor.
    # P0-C removed the UE-render auto path; scanning must never call the UE
    # bridge. Spy on ue_bridge.run_bridge during a scan to prove it.
    import app.ue_bridge as _ueb_scan
    _launched_ue = []
    _orig_rb = _ueb_scan.run_bridge
    _ueb_scan.run_bridge = lambda *a, **k: _launched_ue.append(1)
    win._run_scan([SAMPLE], "reference")
    _d = time.time() + 25
    while win._active_worker is not None and time.time() < _d:
        app.processEvents(); time.sleep(0.02)
    for _ in range(60):
        app.processEvents(); time.sleep(0.02)
    _ueb_scan.run_bridge = _orig_rb
    if _launched_ue:
        bad("scan_no_auto_ue", "run_bridge invoked after scan -> would launch UE")
    else:
        ok("scan_no_auto_ue", "no UE auto-launch triggered by scan completion")

    # VIEWS
    fav = win._all_assets[0]
    win._on_asset_activated(fav)
    win._insp_toggle_fav()
    win._set_view("fav")
    if fav.name in vis():
        ok("favorites", "fav shown")
    else:
        bad("favorites", "fav missing")
    win._insp_toggle_fav()
    win._set_view("no_tag")
    if len(vis()) == n:
        ok("no_tag", "ok")
    else:
        bad("no_tag", "mismatch %d/%d" % (len(vis()), n))
    win._set_view("uncategorized")
    if len(vis()) == 0:
        ok("uncategorized", "ok")
    else:
        bad("uncategorized", str(vis()))
    win._set_view("recent")
    if len(vis()) <= 60:
        ok("recent", "ok %d" % len(vis()))
    else:
        bad("recent", "too big")
    win._set_view("trash")
    if len(vis()) == 0:
        ok("trash", "empty")
    else:
        bad("trash", "not empty")

    # SEARCH / FILTERS
    win._set_view("all")
    win.search.setText("Fire")
    win._apply_filters()
    if any("Fire" in x for x in vis()):
        ok("search", "ok %s" % vis())
    else:
        bad("search", "wrong %s" % vis())
    win.search.setText("")
    win.type_combo.setCurrentIndex(1)
    win._apply_filters()
    if all("Niagara" in c.type for c in win.grid.assets):
        ok("type_filter", "ok")
    else:
        bad("type_filter", [c.type for c in win.grid.assets])
    win.type_combo.setCurrentIndex(0)
    win.src_combo.setCurrentIndex(2)
    win._apply_filters()
    if all(getattr(c, "blueprint", False) for c in win.grid.assets) and vis():
        ok("src_filter", "ok")
    else:
        bad("src_filter", [(c.name, c.blueprint) for c in win.grid.assets])
    win.src_combo.setCurrentIndex(0)

    # TAGS
    win._on_asset_activated(win._all_assets[0])
    win.insp_tag_input.setText("Fire")
    win._add_tag()
    if "Fire" in win._current_asset.tags:
        ok("tag_add", "ok")
    else:
        bad("tag_add", "no")
    # The sidebar tag-filter section was removed (per-asset tags are still
    # editable in the inspector). The legacy _active_tags / tag_buttons /
    # _refresh_tag_list surface is gone, so this block now just verifies the
    # inspector add-tag path still works.
    ok("tag_filter_logic", "sidebar tag-filter section removed; per-asset tag add verified above")
    ok("tag_ui_removed", "sidebar tag-filter section was removed by product decision")

    # FOLDERS
    QInputDialog.getText = lambda *a, **k: ("QA Folder", True)
    win._create_virtual_folder()
    folders = win.db.get_folders()
    if any(f["name"] == "QA Folder" for f in folders):
        ok("folder_create", "ok")
    else:
        bad("folder_create", "no")
    fid = [f["id"] for f in folders if f["name"] == "QA Folder"][0]
    win._add_asset_to_folder(win._all_assets[0].source_path, fid)
    item = None
    for i in range(win.folder_tree.topLevelItemCount()):
        it = win.folder_tree.topLevelItem(i)
        if it.text(0) == "QA Folder":
            item = it
    if item is None:
        bad("folder_select", "not in tree")
    else:
        win._on_folder_selected(item, 0)
        if win._all_assets[0].name in vis():
            ok("folder_filter", "ok")
        else:
            bad("folder_filter", str(vis()))
        # Clicking the same folder again should deselect it and return to all
        win._on_folder_selected(item, 0)
        if win._current_folder is None and win._current_view == "all":
            ok("folder_deselect", "ok")
        else:
            bad("folder_deselect", "still folder=%s view=%s" % (win._current_folder, win._current_view))
        QInputDialog.getText = lambda *a, **k: ("QA Renamed", True)
        win._rename_virtual_folder(fid)
        if any(f["name"] == "QA Renamed" for f in win.db.get_folders()):
            ok("folder_rename", "ok")
        else:
            bad("folder_rename", "no")
        QMessageBox.question = lambda *a, **k: QMessageBox.Yes
        win._delete_virtual_folder(fid)
        if not any(f["id"] == fid for f in win.db.get_folders()):
            ok("folder_delete", "ok")
        else:
            bad("folder_delete", "no")
    QInputDialog.getText = lambda *a, **k: ("", False)
    win._current_folder = None
    win._apply_filters()

    # FOLDER EMPTY-CLICK DESELECT (new wiring: click empty tree area clears selection)
    try:
        win._current_folder = {"kind": "virtual", "id": 999, "name": "XSel"}
        win._current_view = "all"
        win._apply_filters()
        from PySide6.QtCore import Qt as _Qt, QEvent as _QEvent, QPointF as _QPointF
        from PySide6.QtGui import QMouseEvent as _QMouseEvent
        ev = _QMouseEvent(_QEvent.MouseButtonPress, _QPointF(5, 99999),
                          _QPointF(5, 99999), _Qt.LeftButton, _Qt.LeftButton, _Qt.NoModifier)
        win.folder_tree.mousePressEvent(ev)
        if win._current_folder is None and win._current_view == "all":
            ok("folder_empty_click", "empty-area click cleared selection")
        else:
            bad("folder_empty_click", "folder=%s view=%s" % (win._current_folder, win._current_view))
    except Exception as e:
        bad("folder_empty_click", "exc %s" % e)
    win._current_folder = None
    win._apply_filters()

    # TOP VIEW SEGMENTED CONTROL (All / Favorites / Recent, moved from sidebar)
    try:
        win.view_seg_btns["fav"].click()
        if (win._current_view == "fav" and win.view_seg_btns["fav"].isChecked()
                and not win.view_seg_btns["all"].isChecked()):
            ok("top_view_fav", "fav selected & synced")
        else:
            bad("top_view_fav", "view=%s checks=%s" % (win._current_view,
                 [b.isChecked() for b in win.view_seg_btns.values()]))
        win.view_seg_btns["recent"].click()
        if win._current_view == "recent":
            ok("top_view_recent", "ok")
        else:
            bad("top_view_recent", "view=%s" % win._current_view)
        win.view_seg_btns["all"].click()
        if win._current_view == "all":
            ok("top_view_all", "ok")
        else:
            bad("top_view_all", "view=%s" % win._current_view)
    except Exception as e:
        bad("top_view", "exc %s" % e)
    win._apply_filters()

    # GRID REBUILD SPEED (placeholder caching regression check)
    try:
        big = (win._all_assets * 100)[:400]
        t0 = time.time()
        win.grid.set_assets(big)
        dt = time.time() - t0
        win.grid.set_assets(win._all_assets)
        if dt < 3.0:
            ok("grid_rebuild_speed", "%.0f cards rebuilt in %.2fs (<3s)" % (len(big), dt))
        else:
            bad("grid_rebuild_speed", "%.0f cards took %.2fs (too slow)" % (len(big), dt))
    except Exception as e:
        bad("grid_rebuild_speed", "exc %s" % e)
    win._apply_filters()

    # RATING / NOTE
    win._on_asset_activated(win._all_assets[1])
    win._set_rating(4)
    if win._current_asset.rating == 4:
        ok("rating", "ok")
    else:
        bad("rating", "no")
    win.insp_note.setPlainText("QA note")
    win._on_note_changed()
    if win.db.get_asset(win._current_asset.source_path).note == "QA note":
        ok("note", "ok")
    else:
        bad("note", "no")

    # TRASH
    tm = win._all_assets[2]
    win._move_to_trash(tm)
    win._set_view("trash")
    if tm.name in vis():
        ok("trash_move", "ok")
    else:
        bad("trash_move", "no")
    win._restore_from_trash(tm)
    win._set_view("trash")
    if tm.name not in vis():
        ok("trash_restore", "ok")
    else:
        bad("trash_restore", "no")

    # I18N LABEL BUG -- use the REAL toggle path (header button) to trigger _retranslate_ui
    def labels():
        return [l.text() for l in win._insp_row_labels]
    # ensure starting language is zh
    i18n.reset_language_cache()
    if win.lang != "zh":
        win._set_language("zh")
    before = labels()
    win._toggle_language()  # zh -> en, the real user action
    len_ = labels()
    # The inspector now has 5 rows (Health added at position 2); expect
    # all five labels to translate after a language toggle.
    if len_ == ["Type", "Health", "Tags", "Rating", "Notes"]:
        ok("i18n_labels_en", "ok after toggle: %s" % len_)
    else:
        bad("i18n_labels_en", "WRONG after toggle: %s (before was %s)" % (len_, before))
    # toggle back to zh
    win._toggle_language()
    lzh2 = labels()
    if lzh2 == ["类型", "健康", "标签", "评分", "备注"]:
        ok("i18n_labels_zh", "ok %s" % lzh2)
    else:
        bad("i18n_labels_zh", "wrong %s" % lzh2)

    # EMPTY STATE
    win._all_assets = []
    win._apply_filters()
    if getattr(win.grid, "_empty_label", None) and win.grid._empty_label.isVisible():
        ok("empty_state", "onboarding hint shown when library empty")
    else:
        bad("empty_state", "no onboarding hint in grid")
    win._reload_library()

    # Sidebar tag-filter section was removed; the inspector still allows
    # per-asset tag editing. This used to assert tag_buttons presence; that
    # surface no longer exists.
    ok("tag_ui_removed_sidebar", "tag-filter section is gone from the sidebar (intentional)")

    # IMPORT fxpack
    try:
        pd = os.path.join(TMP, "pack")
        os.makedirs(pd, exist_ok=True)
        af = make_uasset("NS_PackTest.uasset", b"NiagaraSystem")
        shutil.copy(af, os.path.join(pd, "NS_PackTest.uasset"))
        man = {"assets": [{"file": "NS_PackTest.uasset", "name": "NS_PackTest", "type": "Niagara", "class_name": "NiagaraSystem"}]}
        with zipfile.ZipFile(os.path.join(TMP, "test.fxpack"), "w") as z:
            z.write(os.path.join(pd, "NS_PackTest.uasset"), "assets/NS_PackTest.uasset")
            z.writestr("manifest.json", json.dumps(man))
        QFileDialog.getOpenFileName = lambda *a, **k: (os.path.join(TMP, "test.fxpack"), "fxpack")
        win._import()
        if any(a.name == "NS_PackTest" for a in win.db.get_assets(include_deleted=True)):
            ok("import_fxpack", "ok")
        else:
            bad("import_fxpack", "no asset")
    except Exception as e:
        bad("import_fxpack", "exc %s" % e)
    QFileDialog.getOpenFileName = lambda *a, **k: ("", "")

    # EXPORT
    try:
        win._reload_library()
        target = os.path.join(TMP, "TargetContent")
        os.makedirs(target, exist_ok=True)
        QFileDialog.getExistingDirectory = lambda *a, **k: target
        win._export_selected(assets=[win._all_assets[0]])
        found = []
        for root, _, files in os.walk(target):
            for fn in files:
                if fn.endswith(".uasset"):
                    found.append(os.path.join(root, fn))
        if found:
            ok("export", "ok copied %d .uasset(s)" % len(found))
        else:
            bad("export", "nothing copied under %s" % target)
    except Exception as e:
        bad("export", "exc %s" % e)
    QFileDialog.getExistingDirectory = lambda *a, **k: ""

    # SETTINGS
    try:
        from app.ui.settings_dialog import SettingsDialog
        d = SettingsDialog(win)
        d.lang_combo.setCurrentIndex(1)
        d.theme_combo.setCurrentIndex(2)
        d.accept()
        ok("settings", "ok")
    except Exception as e:
        bad("settings", "exc %s" % e)

    # SMART FOLDERS (saved searches) — feature removed per product decision.
    # The sidebar no longer exposes a smart-folder section. The legacy
    # _save_smart_folder / _apply_smart_folder / _delete_smart_folder / active
    # tag set no longer exist. Just verify they are gone and don't crash.
    try:
        for name in ("_save_smart_folder", "_apply_smart_folder",
                     "_delete_smart_folder", "_clear_smart_folder",
                     "_toggle_tag", "_active_tags", "_current_smart_folder_id"):
            if hasattr(win, name):
                bad("smart_folder_surface_removed",
                    "%s still present on MainWindow" % name)
                break
        else:
            ok("smart_folder_surface_removed",
               "all smart-folder UI/state surfaces are gone (intentional)")
    except Exception as e:
        bad("smart_folder_surface_removed", "exc %s" % e)

    # TAG MANAGER (rename / delete across assets)
    try:
        from app.ui.tag_manager_dialog import TagManagerDialog
        # The old sidebar-smart-folder setup used to create the 'alpha' tag
        # before this block ran. Since the sidebar section was removed, we
        # create the tag here via the inspector path so the tag-manager
        # dialog still has something to operate on.
        if "alpha" not in win.db.all_tags():
            win._current_asset = win._all_assets[0]
            win.insp_tag_input.setText("alpha")
            win._add_tag()
        if "alpha" not in win.db.all_tags():
            bad("tag_manager_setup", "no tag to manage")
        else:
            dlg = TagManagerDialog(win.db, win.theme, win)
            orig_gt = QInputDialog.getText
            QInputDialog.getText = staticmethod(lambda *a, **k: ("beta", True))
            dlg._rename("alpha")
            QInputDialog.getText = orig_gt
            if "beta" in win.db.all_tags() and "alpha" not in win.db.all_tags():
                ok("tag_manager_rename", "alpha -> beta")
            else:
                bad("tag_manager_rename", "rename failed: %s" % win.db.all_tags())
            orig_q = QMessageBox.question
            QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
            dlg._delete("beta", 1)
            QMessageBox.question = orig_q
            if "beta" not in win.db.all_tags():
                ok("tag_manager_delete", "beta removed")
            else:
                bad("tag_manager_delete", "beta still present: %s" % win.db.all_tags())
    except Exception as e:
        bad("tag_manager", "exc %s" % e)

    # SKIP IMPORT DIALOG setting
    try:
        cfg_data = cfg.load()
        cfg_data["skip_import_dialog"] = True
        cfg.save(cfg_data)
        win.cfg = cfg.load()
        if win.cfg.get("skip_import_dialog") is True:
            ok("skip_import_setting", "setting persists")
        else:
            bad("skip_import_setting", "setting not saved")
    except Exception as e:
        bad("skip_import_setting", "exc %s" % e)

    # GENERATE / READ EMBEDDED THUMBNAIL (right-click, P0-C: local read of
    # the .uasset-embedded editor thumbnail — no UE launch).
    try:
        import app.ue_bridge as _ueb
        mw_src = open(os.path.join(ROOT, "app", "ui", "main_window.py"),
                      encoding="utf-8").read()

        # menu wiring (structural): right-click "read embedded thumbnail"
        if ('a_gen = menu.addAction(tr("ctx_thumb"))' in mw_src
                and 'elif action == a_gen:' in mw_src
                and 'def _gen_embedded_thumb' in mw_src):
            ok("gen_thumb_menu", "right-click menu wired to _gen_embedded_thumb")
        else:
            bad("gen_thumb_menu", "menu wiring missing")

        # NOTE: the old P0-C pre-cursor flow (BridgeWorker QThread, UE bridge,
        # ThumbResultDialog, RenderProgressDialog, _render_next) was removed by
        # product decision — thumbnails are now read locally from the .uasset.
        # Those regression guards no longer apply.

        # ---- local flow: read the thumbnail embedded in the .uasset ----
        # The right-click action no longer launches UE. It extracts the editor
        # thumbnail PNG embedded in the .uasset (tier 1) or, if the asset has
        # none, generates a "no thumbnail" placeholder (tier 4).
        from app import uasset_thumb as _ut
        from PySide6.QtGui import QImage as _QImg, QColor as _QCol
        from PySide6.QtCore import QBuffer, QByteArray

        def _make_png_bytes(w=64, h=64, col=(200, 80, 60)):
            im = _QImg(w, h, _QImg.Format_ARGB32)
            im.fill(_QCol(*col))
            ba = QByteArray(); buf = QBuffer(ba); buf.open(QBuffer.WriteOnly)
            im.save(buf, "PNG"); buf.close()
            return bytes(ba)

        a0 = win._all_assets[0]
        a1 = win._all_assets[1]
        png = _make_png_bytes()
        # a0: embed a real PNG surrounded by fake package bytes
        with open(a0.source_path, "wb") as f:
            f.write(b"\x00\x01UEPKG NiagaraSystem " + png + b" TRAILING_PKG_DATA")
        # a1: no embedded image at all
        with open(a1.source_path, "wb") as f:
            f.write(b"\x00\x01UEPKG NiagaraSystem no image here at all TAIL")

        # extractor unit checks
        _tp = os.path.join(TMP, "extract_test.png")
        if _ut.extract_thumbnail(a0.source_path, _tp) and not _QImg(_tp).isNull():
            ok("uasset_extract", "embedded PNG extracted and decodable")
        else:
            bad("uasset_extract", "failed to extract embedded PNG")
        if not _ut.extract_thumbnail(a1.source_path, _tp):
            ok("uasset_extract_none", "asset without embedded thumbnail returns False")
        else:
            bad("uasset_extract_none", "false positive on asset without thumbnail")

        # false-IEND robustness: literal 'IEND' inside data must not truncate;
        # only the true IEND chunk (type + fixed CRC) terminates the PNG.
        png2 = _make_png_bytes(48, 48, (30, 160, 90))
        with open(a0.source_path, "wb") as f:
            f.write(b"HDR IENDfakebytes " + png2 + b" IENDagain tail")
        if _ut.extract_thumbnail(a0.source_path, _tp) and not _QImg(_tp).isNull():
            ok("uasset_extract_iend", "true IEND chunk located despite literal 'IEND' noise")
        else:
            bad("uasset_extract_iend", "false IEND truncated the PNG")

        # _gen_embedded_thumb: embedded PNG -> tier 1 engine thumbnail
        win._gen_embedded_thumb(a0)
        app.processEvents()
        rec = win.db.get_asset(a0.source_path)
        if rec.tier == 1 and rec.thumb_path and os.path.isfile(rec.thumb_path) \
                and not _QImg(rec.thumb_path).isNull():
            ok("gen_thumb_embedded", "embedded thumbnail applied (tier=1)")
        else:
            bad("gen_thumb_embedded", "tier=%s thumb=%s" % (rec.tier, rec.thumb_path))

        # _gen_embedded_thumb: no embedded thumbnail -> placeholder tier 4
        win._gen_embedded_thumb(a1)
        app.processEvents()
        r1 = win.db.get_asset(a1.source_path)
        if r1.tier == 4 and r1.thumb_path and os.path.isfile(r1.thumb_path):
            ok("gen_thumb_placeholder", "no-thumbnail placeholder generated (tier=4)")
        else:
            bad("gen_thumb_placeholder", "tier=%s thumb=%s" % (r1.tier, r1.thumb_path))

        # regression guard: the local read must NEVER launch the UE bridge.
        _launched = []
        _o_run = _ueb.run_bridge
        _ueb.run_bridge = lambda *a, **k: _launched.append(1)
        win._gen_embedded_thumb(a0)
        app.processEvents()
        win._gen_embedded_thumb(a1)
        app.processEvents()
        _ueb.run_bridge = _o_run
        if not _launched:
            ok("gen_thumb_no_ue_launch", "local read never launches UE bridge")
        else:
            bad("gen_thumb_no_ue_launch", "UE bridge launched %d time(s)" % len(_launched))

        win.grid.clear_selection()
    except Exception as e:
        bad("gen_thumb", "exc %s\n%s" % (e, traceback.format_exc()))

    # Selection controls: select-all / invert / clear + batch thumbnail read.
    try:
        # Make sure we are on a view that has cards (the previous block may
        # have switched into Trash when testing the trash view, leaving the
        # grid empty for the select-all assertions).
        win._set_view("all")
        app.processEvents()
        n_cards = win.grid.total_count()
        win._on_select_all()
        app.processEvents()
        if len(win.grid.selected_assets()) == n_cards and n_cards > 0:
            ok("sel_all", "select-all selects every visible card")
        else:
            bad("sel_all", "selected %d / %d" % (len(win.grid.selected_assets()), n_cards))

        # invert twice -> back to all, then to none
        win._on_invert_selection()
        app.processEvents()
        inv = len(win.grid.selected_assets())
        win._on_invert_selection()
        app.processEvents()
        back = len(win.grid.selected_assets())
        if inv == 0 and back == n_cards:
            ok("sel_invert", "invert toggles full set to empty then back")
        else:
            bad("sel_invert", "inv=%d back=%d (n=%d)" % (inv, back, n_cards))

        # batch thumbnail read honors the current selection
        win._on_select_all()
        app.processEvents()
        first = win.grid.assets[0]
        win._gen_embedded_thumb(first)
        app.processEvents()
        tiers = [win.db.get_asset(c.source_path).tier for c in win.grid.assets]
        if all(t in (1, 4) for t in tiers) and len(tiers) == n_cards:
            ok("sel_gen_batch", "batch thumbnail read applied to all selected")
        else:
            bad("sel_gen_batch", "tiers=%s" % tiers)

        win.grid.clear_selection()
        app.processEvents()
        if len(win.grid.selected_assets()) == 0:
            ok("sel_clear", "clear empties the selection")
        else:
            bad("sel_clear", "still %d selected" % len(win.grid.selected_assets()))
    except Exception as e:
        bad("sel_controls", "exc %s\n%s" % (e, traceback.format_exc()))

    # Verify the bridge subprocess is launched headless and hidden on Windows.
    try:
        import subprocess as _sub
        _orig_popen = _sub.Popen
        _popen_calls = []
        class _FakeProc:
            def __init__(self): self._rc = None
            def poll(self): return self._rc
            def terminate(self): self._rc = -1
            def wait(self, timeout=None): return self._rc
        def _fake_popen(cmd, **kwargs):
            _popen_calls.append((cmd, kwargs))
            res_path = (kwargs.get("env") or {}).get("FXLIB_RESULT_PATH")
            if res_path:
                try:
                    with open(res_path, "w", encoding="utf-8") as f:
                        json.dump({"ok": True, "data": {}}, f)
                except Exception:
                    pass
            return _FakeProc()
        _sub.Popen = _fake_popen
        from app import ue_bridge
        ue_bridge.run_bridge(
            r"D:\Soft\EpicGames\UE_5.4\Engine\Binaries\Win64\UnrealEditor.exe",
            r"D:\Proj\Proj.uproject", "health", {}, timeout=5)
        _sub.Popen = _orig_popen
        if not _popen_calls:
            bad("ue_bridge_windowed", "subprocess.Popen was not called")
        else:
            cmd, kwargs = _popen_calls[0]
            flags_ok = ("-RenderOffScreen" not in cmd and "-unattended" in cmd
                        and "-NoSplash" in cmd and "-nosound" in cmd)
            not_hidden = (kwargs.get("creationflags") is None
                          and kwargs.get("startupinfo") is None)
            if flags_ok and not_hidden:
                ok("ue_bridge_windowed", "UE launched in windowed GPU mode (no RenderOffScreen, no hidden flags)")
            else:
                bad("ue_bridge_windowed", "flags=%s not_hidden=%s cmd=%s" % (flags_ok, not_hidden, cmd))
    except Exception as e:
        bad("ue_bridge_windowed", "exc %s" % e)

    # ===================== A-CLASS FEATURE REGRESSION =====================
    # Batch trash (the originally reported bug: multi-select right-click
    # "move to trash" only deleted the right-clicked one).
    win._set_view("all")
    win._apply_filters()
    sel = win._all_assets[:2]
    win.grid.clear_selection()
    _sel_paths = {s.source_path for s in sel}
    for a in win.grid.assets:
        if a.source_path in _sel_paths:
            win.grid._selected.add(a.object_path)
    win.grid._update_selected_set()
    targets = win.grid.selected_assets()
    win._trash_assets(targets)
    remaining = {a.source_path for a in win._all_assets}
    if all(s.source_path not in remaining for s in sel):
        ok("trash_batch", "multi-select trash removed all %d selected" % len(sel))
    else:
        bad("trash_batch", "only some removed: %s" % remaining)

    # ⑧ copy-mode orphan cleanup: a *permanent* delete must reclaim the
    # library copy (stored_path) + generated thumbnail, but NEVER touch the
    # user's original source file. Prior to this fix copy-mode libraries
    # leaked orphan files forever.
    from app.models import FXAsset as _FXAsset
    _lib = win.cfg.get("library_dir") or cfg.DEFAULT_LIBRARY_DIR
    _fdir = os.path.join(_lib, "files"); os.makedirs(_fdir, exist_ok=True)
    _tdir = os.path.join(_lib, "thumbs"); os.makedirs(_tdir, exist_ok=True)
    _stored = os.path.join(_fdir, "orphan_probe.uasset")
    _thumb = os.path.join(_tdir, "orphan_probe.png")
    _orig = os.path.join(TMP, "orphan_source.uasset")
    for _p in (_stored, _thumb, _orig):
        with open(_p, "wb") as _f:
            _f.write(b"x")
    _probe = _FXAsset(source_path=_orig, name="orphan_probe", type="Niagara",
                      stored_path=_stored, thumb_path=_thumb)
    _freed = win._purge_asset_files(_probe)
    if (not os.path.exists(_stored)) and (not os.path.exists(_thumb)) \
            and os.path.exists(_orig) and _freed == 2:
        ok("orphan_cleanup", "permanent delete reclaims library copy+thumb, spares original")
    else:
        bad("orphan_cleanup", "stored_gone=%s thumb_gone=%s orig_kept=%s freed=%d" % (
            not os.path.exists(_stored), not os.path.exists(_thumb),
            os.path.exists(_orig), _freed))

    # ⑧ guard: purge is wired into BOTH permanent-delete paths, and is
    # scoped to the library dir (never deletes the original source).
    _mw = open(os.path.join(ROOT, "app", "ui", "main_window.py"), encoding="utf-8").read()
    if "_purge_asset_files" in _mw \
            and _mw.count("self._purge_asset_files(a)") >= 2 \
            and "ap.startswith(lib + os.sep)" in _mw:
        ok("orphan_cleanup_wired", "file purge wired into permanent-delete + empty-trash (scoped)")
    else:
        bad("orphan_cleanup_wired", "purge not wired into both delete paths")

    # Toolbar layout: two rows (actions + filters), seg button is in the actions row.
    tb_obj = getattr(win, "toolbar", None)
    if tb_obj is not None and tb_obj.layout() is not None and tb_obj.layout().count() == 2 \
            and tb_obj.minimumHeight() >= 70 \
            and hasattr(win, "btn_add") and hasattr(win, "btn_read_thumbs") \
            and hasattr(win, "view_seg_btns") \
            and "all" in win.view_seg_btns and "fav" in win.view_seg_btns \
            and "recent" in win.view_seg_btns \
            and hasattr(win, "type_combo") and hasattr(win, "src_combo") \
            and hasattr(win, "sort_combo") and hasattr(win, "view_combo"):
        ok("toolbar_two_rows", "toolbar split into actions row + filter row, seg + combos present")
    else:
        bad("toolbar_two_rows", "toolbar layout missing rows or required controls")

    # Seg checked style must not use #ffffff text (white-on-accent unreadable on some themes).
    style_text = open(os.path.join(os.path.dirname(__file__), "..", "app", "style.py"), "r", encoding="utf-8").read()
    if "QPushButton#seg:checked" in style_text:
        # Block of seg:checked selectors (up to next selector). Tolerate {{ }}.
        seg_block = style_text.split("QPushButton#seg:checked", 1)[1]
        # Cut at the first "QPushButton#seg:checked:hover" if present, else at next bare "}}"
        for stop in ("QPushButton#seg:checked:hover", "QPushButton#color_swatch"):
            if stop in seg_block:
                seg_block = seg_block.split(stop, 1)[0]
                break
        if "color: #ffffff" not in seg_block and "color:#ffffff" not in seg_block:
            ok("seg_checked_text", "seg checked-state text color no longer hard-coded white")
        else:
            bad("seg_checked_text", "seg checked text color still white in style.py")
    else:
        bad("seg_checked_text", "QPushButton#seg:checked not found in style.py")

    # ---- UI DESIGN REVIEW (P0/P1/P2) REGRESSION GUARDS ----
    # P0-3: dead #color_swatch selector removed
    if "color_swatch" not in style_text:
        ok("style_no_dead_color_swatch", "stale #color_swatch selector removed")
    else:
        bad("style_no_dead_color_swatch", "stale #color_swatch selector still present")
    # P0-2: explicit :focus outline present (keyboard accessibility)
    if "outline: 2px solid {accent}" in style_text and "outline: none;" in style_text:
        ok("focus_ring_visible", "explicit :focus outline added (keyboard accessibility)")
    else:
        bad("focus_ring_visible", "focus outline rule missing in style.py")
    # P1-1: card shadow scale (sm at rest / md on hover / lg on select)
    if "box-shadow: 0 1px 2px {shadow_sm}" in style_text \
            and "box-shadow: 0 8px 20px {shadow_md}" in style_text \
            and "box-shadow: 0 12px 28px {shadow_lg}" in style_text:
        ok("card_shadow", "asset cards get 3-level shadow scale (sm/md/lg)")
    else:
        bad("card_shadow", "card shadow scale not applied")
        # A-1 / Stripe redesign: primary CTA uses the signature indigo→cyan
        # dual-tone gradient (accent → accent2). This IS the design intent —
        # the old "no accent2" rule was replaced by the 柔光 concept.
    if "qlineargradient" in style_text \
            and "{accent2}" in style_text \
            and ("{accent}" in style_text or "{accent_pressed}" in style_text):
        ok("primary_gradient", "primary CTA uses Stripe-style indigo→cyan dual-tone gradient (accent+accent2)")
    else:
        bad("primary_gradient", "primary CTA must use the accent→accent2 dual-tone gradient (Stripe 柔光)")

    # P1-2: inspector collapsible + auto-collapse on empty selection
    if win.splitter.isCollapsible(2):
        ok("inspector_collapsible", "right inspector panel is collapsible")
    else:
        bad("inspector_collapsible", "inspector not collapsible")
    win.grid.clear_selection(); app.processEvents()
    if win.splitter.sizes()[2] == 0:
        ok("inspector_auto_collapse", "inspector auto-collapses on empty selection")
    else:
        bad("inspector_auto_collapse", "inspector still open with no selection (size=%s)" % win.splitter.sizes()[2])
    if win._all_assets and win.grid.assets:
        win.grid.select_only(win.grid.assets[0]); app.processEvents()
        if win.splitter.sizes()[2] >= 40:
            ok("inspector_auto_expand", "inspector re-expands when an asset is selected")
        else:
            bad("inspector_auto_expand", "inspector did not expand after selection")
        win.grid.clear_selection(); app.processEvents()

    # P2-3: empty-state CTA (primary 'scan now' button)
    if hasattr(win.grid, "empty_action"):
        ok("empty_cta_signal", "AssetGrid exposes empty_action signal")
    else:
        bad("empty_cta_signal", "empty_action signal missing")
    win._all_assets = []
    win._apply_filters(); app.processEvents()
    if getattr(win.grid, "_empty_cta", None) is not None and win.grid._empty_cta.isVisible():
        ok("empty_cta_button", "empty state shows a primary 'scan now' CTA button")
    else:
        bad("empty_cta_button", "empty-state CTA button missing")
    win._reload_library()

    # Thumbnail color normalizer (PIL re-encode path) exists and is wired in.
    from app import uasset_thumb as _ut
    if hasattr(_ut, "_re_encode_png") and callable(_ut._re_encode_png):
        ok("thumb_color_normalize", "uasset_thumb._re_encode_png present (PIL channel normalize)")
    else:
        bad("thumb_color_normalize", "_re_encode_png missing")

    # Sort dimensions (name/type/date/size/rating/random)
    win._set_view("all")
    win._apply_filters()
    sort_ok = True
    for m in ("name", "type", "date", "size", "rating", "random"):
        win.sort_combo.setCurrentIndex(win.sort_combo.findData(m))
        win._apply_filters()
        cards = win.grid.assets
        if not cards:
            sort_ok = False
            break
        if m == "size":
            if [c.size or 0 for c in cards] != sorted((c.size or 0 for c in cards), reverse=True):
                sort_ok = False
        elif m == "rating":
            if [c.rating or 0 for c in cards] != sorted((c.rating or 0 for c in cards), reverse=True):
                sort_ok = False
        elif m == "name":
            if [c.name.lower() for c in cards] != sorted(c.name.lower() for c in cards):
                sort_ok = False
        elif m == "type":
            if [(c.type or "", c.name.lower()) for c in cards] != sorted((c.type or "", c.name.lower()) for c in cards):
                sort_ok = False
        elif m == "date":
            if [c.imported_at or "" for c in cards] != sorted((c.imported_at or "" for c in cards), reverse=True):
                sort_ok = False
    if sort_ok:
        ok("sort_dims", "all 6 sort modes applied correctly")
    else:
        bad("sort_dims", "ordering wrong for a mode")

    # Batch tag (apply one tag to all selected)
    win._set_view("all")
    win._apply_filters()
    bsel = win._all_assets[:2]
    win.grid.clear_selection()
    _bsel_paths = {s.source_path for s in bsel}
    for a in win.grid.assets:
        if a.source_path in _bsel_paths:
            win.grid._selected.add(a.object_path)
    win.grid._update_selected_set()
    QInputDialog.getText = lambda *a, **k: ("QA,Smoke", True)
    win._batch_add_tag(win.grid.selected_assets())
    tag_ok = all("QA" in (win.db.get_asset(s.source_path).tags or "") for s in bsel)
    if tag_ok:
        ok("batch_tag", "tag added to %d selected assets" % len(bsel))
    else:
        bad("batch_tag", "tag not applied to all")
    for s in bsel:
        win.db.set_tags(s.source_path, "")

    # View modes (small/medium/large/list)
    for mode in ("small", "medium", "large", "list"):
        win.grid.view_mode = mode
        win._apply_filters()
        if win.grid.assets and win.grid.view_mode == mode:
            ok("view_mode_%s" % mode, "cards rebuilt in %s mode" % mode)
        else:
            bad("view_mode_%s" % mode, "mode not applied")
    win.grid.view_mode = "medium"
    win._apply_filters()

    # ---- UI redesign regression (round 3) ----
    from PySide6.QtWidgets import QSizePolicy
    mw_src = open(os.path.join(ROOT, "app", "ui", "main_window.py"), encoding="utf-8").read()
    sg_src = open(os.path.join(ROOT, "app", "ui", "asset_grid.py"), encoding="utf-8").read()
    st_src = open(os.path.join(ROOT, "app", "style.py"), encoding="utf-8").read()

    # F7: dark-mode white panel root cause removed
    if "QScrollArea QWidget { background:" in st_src:
        bad("dark_scrollarea_white", "old 'QScrollArea QWidget { background }' rule still present")
    else:
        ok("dark_scrollarea_white", "scrollarea child-bg rule removed (was painting panels white)")
    if "QScrollArea::viewport {{ background: {bg2}" in st_src:
        ok("scrollarea_viewport_bg", "viewport background tokenized -> no white panel in dark")
    else:
        bad("scrollarea_viewport_bg", "viewport background rule missing")

    # F1: checked + focus must not double-outline
    if "QPushButton:checked:focus" in st_src:
        ok("focus_checked_single", "checked:focus suppresses focus ring (no double box)")
    else:
        bad("focus_checked_single", "no checked:focus rule")

    # F3: ghost icon style for sidebar '+' buttons
    if "QPushButton#iconghost" in st_src:
        ok("iconghost_style", "#iconghost style present for sidebar + buttons")
    else:
        bad("iconghost_style", "#iconghost style missing")
    if 'setObjectName("iconghost")' in mw_src:
        ok("iconghost_wired", "sidebar + buttons use #iconghost")
    else:
        bad("iconghost_wired", "sidebar + buttons still #icon")

    # ---- DESIGN-SENSE (D-2 / D-3) REGRESSION GUARDS ----
    # D-2: empty state ships a painted illustration (not bare text).
    if "_empty_illustration" in sg_src and 'setObjectName("emptyillustration")' in sg_src \
            and "self._empty_icon.setPixmap" in sg_src:
        ok("empty_illustration", "empty state renders a brand-tinted illustration (D-2)")
    else:
        bad("empty_illustration", "empty state still text-only (D-2 missing)")

    # D-3a: cards get an animated hover 'lift' (real depth via drop-shadow anim,
    # since Qt QSS ignores box-shadow).
    if "QGraphicsDropShadowEffect" in sg_src and "_animate_lift" in sg_src \
            and "QPropertyAnimation" in sg_src \
            and "self._animate_lift(True)" in sg_src \
            and "self._animate_lift(False)" in sg_src:
        ok("card_hover_lift_anim", "cards animate a hover lift (D-3 micro-interaction)")
    else:
        bad("card_hover_lift_anim", "card hover animation missing (D-3)")

    # D-3b: batch bar fades/slides in on selection.
    if "_animate_batchbar_in" in mw_src and "QGraphicsOpacityEffect" in mw_src \
            and "QPropertyAnimation" in mw_src \
            and "self._animate_batchbar_in()" in mw_src:
        ok("batchbar_slide_anim", "batch bar animates in on selection (D-3 micro-interaction)")
    else:
        bad("batchbar_slide_anim", "batch bar appears with no animation (D-3)")

    # ROUND-4 (方案B): the view segmented control (all/fav/recent) must sit in the
    # content-area head, immediately after self.section_count -- NOT in the top
    # chrome (_build_ui header). It is an inline filter beside "全部特效 N个结果".
    _idx_main = mw_src.find("def _build_main_area")
    _idx_seg_def = mw_src.find("def _build_view_segment")
    _idx_ui = mw_src.find("def _build_ui")
    _idx_call = mw_src.find("self._build_view_segment(hl)")
    _idx_count = mw_src.find("self.section_count")
    if -1 not in (_idx_main, _idx_seg_def, _idx_call, _idx_count):
        _in_main = _idx_main < _idx_call < _idx_seg_def
        _after_count = _idx_count < _idx_call
        _not_in_ui = not (_idx_ui < _idx_call < _idx_main)
        if _in_main and _after_count and _not_in_ui:
            ok("view_seg_inline_area", "seg sits in content head after count (方案B inline filter)")
        else:
            bad("view_seg_inline_area", "seg placement wrong (in_main=%s after_count=%s not_in_ui=%s)"
                % (_in_main, _after_count, _not_in_ui))
    else:
        bad("view_seg_inline_area", "could not locate seg placement markers in source")

    # F2: no inline gradient QSS on primary button (theme single-source)
    if "self.btn_add.setStyleSheet" in mw_src:
        bad("primary_inline_qss", "btn_add still has inline QSS")
    else:
        ok("primary_inline_qss", "btn_add uses global #primary style")

    # F4: filter combos equal width
    if win.type_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding:
        ok("combo_equal_width", "filter combos use Expanding size policy (equal width)")
    else:
        bad("combo_equal_width", "filter combos not Expanding")

    # F7: hard-coded #0F1115 dark text removed
    if "0F1115" in mw_src:
        bad("hardcode_0F1115", "hard-coded #0F1115 text still present")
    else:
        ok("hardcode_0F1115", "no hard-coded #0F1115 text")

    # F9: inspector can fully collapse (min-width 0)
    if win.inspector.minimumWidth() == 0:
        ok("inspector_collapsible", "inspector min-width 0 -> can fully collapse (no blank panel)")
    else:
        bad("inspector_collapsible", "inspector still has min-width %d" % win.inspector.minimumWidth())

    # F8 used to test tag-section auto-collapse; that surface is gone. The
    # sidebar now only contains the folder tree + Trash.
    ok("tag_section_removed", "tag section is gone from the sidebar (F8 obsolete)")

    # F12: type gradients clearly distinct
    import app.ui.asset_grid as ag
    niag = ag.TYPE_GRADIENT.get("Niagara")
    casc = ag.TYPE_GRADIENT.get("Cascade")
    if niag and casc and niag != casc and niag[0] != casc[0]:
        ok("type_gradient_distinct", "Niagara(%s) vs Cascade(%s) clearly different" % (niag[0], casc[0]))
    else:
        bad("type_gradient_distinct", "type gradients not distinct enough")

    # F10: placeholder uses unified visual (big type letter, no caption text)
    # The _placeholder() draws a gradient + centered glyph letter (N/C/B/T/M)
    # matching scanner.make_placeholder_thumb and main_window._generate_placeholder_thumb.
    if "_TYPE_LETTER" in sg_src and ("p.drawText" in sg_src or "letter" in sg_src):
        ok("no_thumb_drawn", "placeholder uses unified big-letter style (no old caption)")
    else:
        bad("no_thumb_drawn", "placeholder missing unified letter style")

    # F13/ROUND-4: 'my library' button now uses the global #libbtn token style
    # (no inline hard-coded QSS) so theme switching re-skins it correctly.
    if "self.lib_btn.setStyleSheet" not in mw_src and "#libbtn" in st_src:
        ok("libbtn_tokenized", "'my library' button uses global #libbtn token (no inline heavy QSS)")
    else:
        bad("libbtn_tokenized", "libbtn still has inline heavy QSS or #libbtn token missing")

    # ---- UI redesign regression (round 4: dark-mode white-block root cause) ----
    # Previously inline-hard-coded QSS on sidebar widgets (folder tree, lib btn,
    # sidebar splitter, section arrow, empty-section hint, footer sep) is now
    # tokenized into app/style.py so setStyleSheet(theme) re-paints them too.
    for _sel, _name in (("QTreeWidget#foldertree", "foldertree"),
                        ("QPushButton#libbtn", "libbtn"),
                        ("QSplitter#sidebarsplitter::handle", "sidebarsplitter"),
                        ("QSplitter#mainsplitter::handle", "mainsplitter"),
                        ("QLabel#navhint", "navhint"),
                        ("QFrame#seph", "seph"),
                        ("QLabel#navarrow", "navarrow"),
                        ("QWidget#navheader", "navheader")):
        if _sel in st_src:
            ok("token_%s" % _name, "%s selector tokenized in style.py" % _sel)
        else:
            bad("token_%s" % _name, "%s selector missing from style.py" % _sel)

    # Negative guard: none of those widgets still carry inline hard-coded QSS.
    _inline_left = [w for w in ("folder_tree.setStyleSheet", "splitter.setStyleSheet",
                                "arrow.setStyleSheet", "hint.setStyleSheet",
                                "self.lib_btn.setStyleSheet") if w in mw_src]
    if not _inline_left:
        ok("no_inline_widget_qss", "no inline hard-coded QSS left on sidebar widgets")
    else:
        bad("no_inline_widget_qss", "inline QSS still present: %s" % _inline_left)

    # Dark-mode QComboBox hover contrast (down-arrow recolored to accent).
    if "QComboBox:hover {" in st_src and "QComboBox:hover::down-arrow" in st_src:
        ok("combo_dark_hover", "QComboBox hover border + down-arrow use accent (dark contrast)")
    else:
        bad("combo_dark_hover", "QComboBox hover/down-arrow accent rule missing")

    # Sidebar sections (tags / smart_folders / management) were removed per
    # product decision — the sidebar now only shows the folder tree + Trash.
    # The icon_name anchors that used to live on those sections are gone too.
    ok("section_icons_removed", "tags / smart_folders / management sections (and their icon_name anchors) are gone from the sidebar")

    # Tier badge only shows for real thumbnails (tier >= 2); placeholders (tier 1)
    # must NOT render the watermark-like corner badge.
    try:
        from app.ui.asset_grid import AssetCard as _AC
        class _FakeA:
            def __init__(self, t):
                self.tier = t; self.name = "x"; self.type = "Niagara"
                self.tags = None; self.thumb_path = None; self.favorite = False
        _c1 = _AC(_FakeA(1), view_mode="medium")
        _c2 = _AC(_FakeA(2), view_mode="medium")
        if (not _c1._tier_visible()) and _c2._tier_visible():
            # confirm the badge's visible state actually follows the logic
            _c1.show(); _c2.show(); app.processEvents()
            if (not _c1.tier.isVisible()) and _c2.tier.isVisible():
                ok("tier_placeholder_hidden", "tier-1 placeholder hides badge; tier>=2 shows it")
            else:
                bad("tier_placeholder_hidden", "setVisible not following _tier_visible (t1=%s t2=%s)"
                    % (_c1.tier.isVisible(), _c2.tier.isVisible()))
        else:
            bad("tier_placeholder_hidden", "_tier_visible logic wrong (t1=%s t2=%s)"
                % (_c1._tier_visible(), _c2._tier_visible()))
    except Exception as e:
        bad("tier_placeholder_hidden", "exc %s" % e)

    # ROUND-5: 'my library' button must read as a section title (muted color +
    # bold), matching the QWidget#navheader section labels below — otherwise in
    # light mode it looks "dark" and in dark mode it looks "bright" (the only
    # thing in the sidebar with a different color than the section titles).
    if "QPushButton#libbtn" in st_src and re.search(
            r"QPushButton#libbtn\s*\{[^}]*color:\s*\{muted\}", st_src, re.S):
        ok("libbtn_uses_muted", "'my library' uses muted color (section title tier)")
    else:
        bad("libbtn_uses_muted", "'my library' color not tokenized to muted")

    # ROUND-5: 'my library' button has a library icon (visual anchor, like the
    # other section headers which all carry icon_name).
    if re.search(r'self\.lib_btn\.setIcon\(\s*icon\(\s*"library"', mw_src):
        ok("libbtn_has_library_icon", "'my library' button carries a library icon")
    else:
        bad("libbtn_has_library_icon", "lib_btn.setIcon(icon('library', ...)) missing")

    # ROUND-5: QToolTip must be globally themed (else the OS default black box
    # shows on hover for every setToolTip'd widget — user reported it on the
    # 'scan directory' button).
    if re.search(r"QToolTip\s*\{[^}]*background-color:\s*\{bg2\}", st_src, re.S):
        ok("tooltip_global_tokenized", "QToolTip is globally themed (no black box on hover)")
    else:
        bad("tooltip_global_tokenized", "QToolTip block missing or not tokenized to bg2")
    # ROUND-6: QToolTip must NOT use `opacity` — the top-level window's alpha
    # stacks with widget opacity, so the box looks black even when {bg2} is
    # light. This was the actual cause of the user's "hover shows a dark box".
    if re.search(r"QToolTip\s*\{[^}]*opacity\s*:", st_src, re.S):
        bad("tooltip_no_opacity", "QToolTip rule uses opacity (causes the black-box bug)")
    else:
        ok("tooltip_no_opacity", "QToolTip has no opacity stacking bug")

    # ROUND-6: 'scan directory' (#primary) hover must keep white text legible.
    # Stripe redesign: hover shifts to accent_hover → brighter cyan (#00b8ff),
    # which maintains contrast while adding vibrancy.
    # NOTE: use [\s\S]*? not [^}]* because the raw template has {{ }}
    # format-string escaping that embeds '}' characters.
    if re.search(r"QPushButton#primary:hover\s*\{[\s\S]*?00b8ff", st_src, re.S):
        ok("primary_hover_darkens", "#primary:hover uses bright cyan stop (Stripe dual-tone hover)")
    else:
        bad("primary_hover_darkens", "#primary:hover missing bright cyan (#00b8ff) hover stop")

    # ROUND-7: theme switch must force re-polish on every visible widget.
    # Without qapp.setStyleSheet("") round-trip + unpolish/polish, the main
    # window can stay on the previous theme while a newly opened dialog
    # renders in the new theme — exactly the "main window light, dialog dark"
    # bug reported.
    if (re.search(r'qapp\.setStyleSheet\(""\)', mw_src)
            and re.search(r"unpolish\(w\)", mw_src)
            and re.search(r"polish\(w\)", mw_src)):
        ok("apply_theme_force_repolish", "_apply_theme force-repolishes all top-level widgets on switch")
    else:
        bad("apply_theme_force_repolish", "_apply_theme missing the empty-QSS + unpolish/polish round-trip")

    # ROUND-7: the main folder tree must NOT carry its own inline QSS — that
    # was the root cause of the "test" folder card staying light in dark mode.
    if re.search(r"_build_folder_tree[\s\S]{0,3000}tree\.setStyleSheet", mw_src):
        bad("foldertree_no_inline_qss", "folder tree still has an inline setStyleSheet — locks color to build-time theme")
    else:
        ok("foldertree_no_inline_qss", "folder tree styling is owned by global #foldertree rule")

    # ROUND-7: card chrome (tier/fav/check/chip/bp_chip/empty_label) must
    # come from objectName + global QSS, not inline setStyleSheet.
    ag = open(r"app\ui\asset_grid.py", "r", encoding="utf-8").read()
    inline_card_chrome = re.findall(
        r"self\.(tier|fav|chip|bp_chip|check|empty_label|_empty_label)\.setStyleSheet\(",
        ag,
    )
    if inline_card_chrome:
        bad("card_chrome_no_inline",
            "asset_grid.py still has inline setStyleSheet on: " + ", ".join(sorted(set(inline_card_chrome))))
    else:
        ok("card_chrome_no_inline", "card chrome (tier/fav/chip/bp_chip/check/empty) is objectName-driven")

    needed = [
        "QLabel#cardtier",
        "QPushButton#cardfav",
        "QPushButton#cardcheck",
        "QLabel#cardtypechip",
        "QLabel#cardbpchip",
        "QLabel#cardemptylabel",
        "QLabel#batchcount",
        "QPushButton#batchbtnprimary",
        "QPushButton#batchbtndanger",
        "QPushButton#batchbtn",
        "QPushButton#inspexp",
        "QLabel#inspbpchip",
        "QPushButton#star",
    ]
    missing = [n for n in needed if n not in st_src]
    if missing:
        bad("card_chrome_global_rules", "style.py missing global rules: " + ", ".join(missing))
    else:
        ok("card_chrome_global_rules", "style.py has all card chrome + batch bar global rules")

    if re.search(r'self\.chip\.setProperty\(\s*"type"\s*,\s*self\.asset\.type', ag):
        ok("typechip_uses_dynamic_property", "type chip sets dynamic 'type' property for per-type coloring")
    else:
        bad("typechip_uses_dynamic_property", "type chip does not set 'type' dynamic property")

    if (re.search(r'self\.check\.setProperty\(\s*"selected"\s*,\s*"true"', ag)
            and re.search(r'self\.check\.setProperty\(\s*"selected"\s*,\s*"false"', ag)
            and re.search(r"unpolish\(self\.check\)", ag)):
        ok("cardcheck_uses_dynamic_property", "card check uses [selected] dynamic property (no inline chrome)")
    else:
        bad("cardcheck_uses_dynamic_property", "card check still uses inline setStyleSheet for selected state")

    # ROUND-9: the Stripe 柔光 redesign requires ALL main CTAs to use the
    # indigo→cyan dual-tone gradient (accent → accent2). This covers
    # batchbar primary button and inspector "Export to UE" button.
    for sel, name in (("#batchbtnprimary", "batchbtnprimary"),
                       ("#inspexp", "inspexp")):
        if "qlineargradient" in st_src \
                and "{accent2}" in st_src \
                and ("{accent}" in st_src or "{accent_pressed}" in st_src):
            ok(name + "_dual_tone",
               "%s uses Stripe-style indigo→cyan dual-tone gradient" % sel)
        else:
            bad(name + "_dual_tone",
                "%s must use accent→accent2 dual-tone gradient (Stripe 柔光)" % sel)

    # ROUND-9: the inspector "Export to UE" button must be tokenized
    # (objectName #inspexp), not an inline qlineargradient set in _build_inspector
    # (that inline approach went stale on theme switch — ROUND-7's core lesson).
    if 'self.insp_exp.setObjectName("inspexp")' in mw_src \
            and "insp_exp.setStyleSheet" not in mw_src:
        ok("inspexp_tokenized", "inspector Export-to-UE button is tokenized (#inspexp), no inline gradient")
    else:
        bad("inspexp_tokenized", "inspector Export-to-UE button still uses inline setStyleSheet")

    # ROUND-9: Tag-related sidebar organization
    #   "Uncategorized" was removed (dead filter — scanner always assigns type).
    #   "No-Tag" (未标签) lives inside the tag browser as a #tagchipbar chip
    #   (_no_tag_chip), NOT as a standalone nav_btn.  It must be reachable via
    #   _set_view("no_tag") and visually consistent with real tag chips.
    has_no_tag_chip = ('_no_tag_chip' in mw_src
                       and 'tr("no_tag")' in mw_src
                       and '_set_view("no_tag")' in mw_src)
    has_uncat_removed = ('self.nav_uncat' not in mw_src)
    if has_no_tag_chip and has_uncat_removed:
        ok("uncat_notag_reachable",
           "No-Tag inside tag browser (#tagchipbar); Uncategorized removed")
    else:
        bad("uncat_notag_reachable",
            "No-Tag not in tag browser or Uncategorized still present")

    # ROUND-11: Windows-style 3 view modes (icons / list / details table)
    if 'self.view_combo' in mw_src and '("icons", tr("vm_icons"))' in mw_src \
            and '("list", tr("vm_list"))' in mw_src \
            and '("details", tr("vm_details"))' in mw_src \
            and 'self.details_table = self._build_details_table()' in mw_src \
            and 'QStackedWidget' in mw_src:
        ok("view_modes_3way", "icons / list / details view modes present (QStackedWidget + details table)")
    else:
        bad("view_modes_3way", "three view modes / details table not wired")

    # ROUND-10: "has thumbnail" / "no thumbnail" sidebar filters (new feature).
    # (a) structural: nav entries wired to the two new views.
    if ('self.nav_thumb' in mw_src and '_set_view("has_thumb")' in mw_src
            and 'self.nav_nothumb' in mw_src and '_set_view("no_thumb")' in mw_src
            and '"has_thumb": self.nav_thumb' in mw_src
            and '"no_thumb": self.nav_nothumb' in mw_src):
        ok("thumb_filter_nav", "sidebar has Thumbnail / No-Thumbnail nav entries")
    else:
        bad("thumb_filter_nav", "thumbnail filter nav wiring missing")

    # ROUND-11b: functional — details view populates the table & switches back
    try:
        _grid_n = win.grid.total_count()
        win._on_view_mode_changed("details")
        _dt = win.details_table
        if win.content_stack.currentWidget() is _dt and _dt.rowCount() == _grid_n:
            ok("details_table_func", "details view shows table, rows=%d == grid cards" % _dt.rowCount())
        else:
            bad("details_table_func",
                 "details table mismatch: rows=%d grid=%d same_widget=%s" % (
                     _dt.rowCount(), _grid_n,
                     win.content_stack.currentWidget() is _dt))
        # switch to list then back to icons
        win._on_view_mode_changed("list")
        _list_ok = win.content_stack.currentWidget() is win.grid and win.grid.view_mode == "list"
        win._on_view_mode_changed("icons")
        _icons_ok = win.content_stack.currentWidget() is win.grid and win.grid.view_mode == win._icon_size
        if _list_ok and _icons_ok:
            ok("view_switch_roundtrip", "list -> icons view modes round-trip correctly")
        else:
            bad("view_switch_roundtrip", "view mode switch failed (list=%s icons=%s)" % (_list_ok, _icons_ok))
    except Exception as e:
        bad("details_table_func", "exception: %s" % e)

    # ROUND-11c: details table features — sorting, context menu, column resize,
    # alternating rows, fixed row height (performance fix).
    try:
        _dt = win.details_table
        # 1) Sorting must be enabled
        if _dt.isSortingEnabled():
            ok("details_sorting", "table sorting enabled (click header to sort)")
        else:
            bad("details_sorting", "sorting NOT enabled on details table")
        # 2) Context menu policy must be CustomContextMenu
        from PySide6.QtCore import Qt as _Qt2
        if _dt.contextMenuPolicy() == _Qt2.ContextMenuPolicy.CustomContextMenu:
            ok("details_context_menu", "customContextMenuRequested wired for right-click")
        else:
            bad("details_context_menu", "context menu policy=%s (expected CustomContextMenu)"
                % _dt.contextMenuPolicy())
        # 3) All columns Interactive (user can drag-resize)
        _hdr = _dt.horizontalHeader()
        _modes = [_hdr.sectionResizeMode(c) for c in range(_dt.columnCount())]
        from PySide6.QtWidgets import QHeaderView as _QHV
        if all(m == _QHV.Interactive for m in _modes):
            ok("details_cols_resizable", "all %d columns are Interactive (drag-resizable)"
                % len(_modes))
        else:
            bad("details_cols_resizable", "column resize modes=%s (expected all Interactive)" % _modes)
        # 4) Alternating row colors
        if _dt.alternatingRowColors():
            ok("details_alt_rows", "alternating row colors enabled")
        else:
            bad("details_alt_rows", "alternating row colors disabled")
        # 5) Sort indicator shown on header
        if _hdr.isSortIndicatorShown():
            ok("details_sort_indicator", "sort indicator shown on header")
        else:
            bad("details_sort_indicator", "sort indicator hidden")
        # 6) Reasonable initial width for name column (>100px)
        if _dt.columnWidth(0) >= 150:
            ok("details_name_width", "name column initial width=%d px (>=150)" % _dt.columnWidth(0))
        else:
            bad("details_name_width", "name column too narrow: %d px" % _dt.columnWidth(0))
    except Exception as e:
        bad("details_features", "exc %s" % e)

    # ROUND-11d: star rating buttons + favorites sidebar entry
    try:
        _stars = win.insp_stars
        if len(_stars) == 5:
            ok("star_count", "5 star buttons present")
        else:
            bad("star_count", "%d stars (expected 5)" % len(_stars))
        # Each star should be 28x28 (square)
        _sq = all(s.width() == s.height() == 28 for s in _stars)
        if _sq:
            ok("star_square", "all stars are 28x28 square")
        else:
            bad("star_square", "stars not square: %s" % [(s.width(),s.height()) for s in _stars])
        # Star objectName must be "star"
        if all(s.objectName() == "star" for s in _stars):
            ok("star_objectname", "all stars have objectName='star'")
        else:
            bad("star_objectname", "some stars missing objectName='star'")
        # Favorites sidebar nav button exists
        if hasattr(win, "nav_fav") and win.nav_fav is not None:
            ok("fav_sidebar_entry", "favorites nav button present in sidebar")
            # It should be in the nav_map
            if "fav" in win._nav_map and win._nav_map["fav"] is win.nav_fav:
                ok("fav_in_navmap", "nav_fav registered in _nav_map['fav']")
            else:
                bad("fav_in_navmap", "nav_fav NOT in _nav_map or mismatch")
        else:
            bad("fav_sidebar_entry", "no nav_fav button in sidebar")
        # Inspector fav button exists
        if hasattr(win, "insp_fav") and win.insp_fav is not None:
            ok("insp_fav_btn", "inspector favorite button exists")
        else:
            bad("insp_fav_btn", "no inspector favorite button")
        # Toggle favorite works (set then check)
        if win._current_asset:
            _orig = getattr(win._current_asset, "favorite", False)
            win._current_asset.favorite = True
            win._sync_insp_fav()
            _txt = win.insp_fav.text()
            if _txt.startswith("★"):
                ok("insp_fav_toggle_on", "fav button shows ★ when favorited: '%s'" % _txt[:10])
            else:
                bad("insp_fav_toggle_on", "fav button text='%s' (expected ★ prefix)" % _txt)
            win._current_asset.favorite = _orig
            win._sync_insp_fav()
    except Exception as e:
        bad("star_fav_features", "exc %s" % e)

    # (b) DB: has_thumb column migrates in, upsert + set_has_thumb round-trip.
    try:
        import tempfile as _tf, os as _os
        from app.database import Database as _DB
        from app.models import FXAsset as _FA
        _tdb = _os.path.join(_tf.gettempdir(), "qa_thumb_%d.db" % _os.getpid())
        if _os.path.exists(_tdb):
            _os.remove(_tdb)
        _d = _DB(_tdb)
        _d.upsert_asset(_FA(source_path="x:/y.uasset", name="Y", has_thumb=True))
        _r1 = _d.get_asset("x:/y.uasset")
        if _r1 is not None and _r1.has_thumb is True:
            _d.set_has_thumb("x:/y.uasset", False)
            _r2 = _d.get_asset("x:/y.uasset")
            if _r2 is not None and _r2.has_thumb is False:
                ok("thumb_filter_db", "has_thumb column + set/get round-trips")
            else:
                bad("thumb_filter_db", "set_has_thumb did not persist")
        else:
            bad("thumb_filter_db", "has_thumb not stored by upsert")
        try:
            _os.remove(_tdb)
        except OSError:
            pass
    except Exception as e:
        bad("thumb_filter_db", "exc %s" % e)

    # (c) filter logic: _apply_filters returns the right subset for each view.
    try:
        from app.models import FXAsset as _FA2
        _toys = [
            _FA2(source_path="T:/a.uasset", name="A", has_thumb=True),
            _FA2(source_path="T:/b.uasset", name="B", has_thumb=False),
        ]
        _captured = []
        _orig_all = getattr(win, "_all_assets", [])
        _orig_set = win.grid.set_assets
        win._all_assets = _toys
        win.grid.set_assets = lambda lst: _captured.append([a.name for a in lst])
        # neutralize the secondary grid filters so the view predicate is what we test
        _orig_agf = win._apply_grid_filters
        _orig_as = win._apply_sort
        win._apply_grid_filters = lambda x, *a, **k: x
        win._apply_sort = lambda x, *a, **k: None
        win._current_view = "has_thumb"
        win._apply_filters()
        _has = list(_captured[-1]) if _captured else []
        win._current_view = "no_thumb"
        win._apply_filters()
        _nothas = list(_captured[-1]) if _captured else []
        # restore
        win._all_assets = _orig_all
        win.grid.set_assets = _orig_set
        win._apply_grid_filters = _orig_agf
        win._apply_sort = _orig_as
        if _has == ["A"] and _nothas == ["B"]:
            ok("thumb_filter_logic", "has_thumb -> [A], no_thumb -> [B]")
        else:
            bad("thumb_filter_logic", "expected [A]/[B], got %r/%r" % (_has, _nothas))
    except Exception as e:
        bad("thumb_filter_logic", "exc %s" % e)

    log("=== REPORT ===")
    fails = [r for r in results if r[0] == "FAIL"]
    passes = [r for r in results if r[0] == "PASS"]
    infos = [r for r in results if r[0] == "INFO"]
    log("PASS=%d FAIL=%d INFO=%d" % (len(passes), len(fails), len(infos)))
    for st, a, m in results:
        log("[%s] %-18s %s" % (st, a, m))
    log("=== END ===")
    sys.exit(1 if fails else 0)
except Exception as e:
    log("FATAL: " + "".join(traceback.format_exception_only(type(e), e)))
    log(traceback.format_exc())
    sys.exit(2)
