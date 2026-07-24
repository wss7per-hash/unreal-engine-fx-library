# fx_thumbnail.py -- headless bridge: thumbnail generation for FX assets.
#
# Two strategies are provided:
#   * try_render()          -> static editor thumbnail (EditorThumbnailSubsystem).
#                               For Niagara this already simulates the system, so it
#                               yields a representative frame; for Cascade it is static.
#   * try_render_playing()  -> spawns the FX system into the editor world, advances the
#                               simulation, and captures a frame via a SceneCapture2D.
#                               This is the "real playing" frame the client asks for.
#                               It is best-effort and version-dependent (headless UE does
#                               not tick the world during a blocking python script), so it
#                               always falls back to try_render() on any failure.
#
# No C++ plugin required; pure-Python via the unreal module.

import os
import sys
import zlib
import struct

sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_common


def _write_png(path, width, height, rgba_bytes):
    """Encode RGBA bytes to a PNG file using only the stdlib (no Pillow needed)."""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        raw.extend(rgba_bytes[y * stride:(y + 1) * stride])
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(sig)
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


def _rt_to_png(rt, out_path):
    """Read pixels from a render target and write them to a PNG. Returns True
    on success. Tries several read_pixels() signatures across UE 5.x."""
    if rt is None:
        return False
    try:
        size_x = int(rt.get_editor_property("size_x"))
        size_y = int(rt.get_editor_property("size_y"))
    except Exception:
        return False
    if size_x <= 0 or size_y <= 0:
        return False

    pixels = None
    getter = getattr(rt, "read_pixels", None)
    if getter is not None:
        # Signature varies: () -> array, or (x, y, w, h) -> array.
        for args in ((), (0, 0, size_x, size_y)):
            try:
                got = getter(*args) if args else getter()
            except Exception:
                got = None
            if got:
                # Some versions return (array, success) tuples.
                if isinstance(got, tuple) and len(got) == 2:
                    got = got[0]
                if got:
                    pixels = got
                    break
    if not pixels:
        return False

    rgba = bytearray()
    for p in pixels:
        r = getattr(p, "r", 0)
        g = getattr(p, "g", 0)
        b = getattr(p, "b", 0)
        a = getattr(p, "a", 255)
        # LinearColor components are 0..1; Color components are 0..255.
        if isinstance(r, float):
            r = int(max(0.0, min(1.0, r)) * 255)
            g = int(max(0.0, min(1.0, g)) * 255)
            b = int(max(0.0, min(1.0, b)) * 255)
            a = int(max(0.0, min(1.0, a)) * 255)
        else:
            r = int(r); g = int(g); b = int(b); a = int(a)
        rgba.append(r); rgba.append(g); rgba.append(b); rgba.append(a)

    try:
        fx_common.ensure_dir(os.path.dirname(out_path))
        _write_png(out_path, size_x, size_y, bytes(rgba))
        return True
    except Exception as e:
        unreal.log_warning("[FXLibrary] PNG write failed: %s" % e)
        return False


def try_render(asset, out_path, size=256):
    """Best-effort: render the editor's static thumbnail for an asset.
    Returns True on success."""
    try:
        ets = unreal.get_editor_subsystem(unreal.EditorThumbnailSubsystem)
    except Exception as e:
        unreal.log_warning("[FXLibrary] EditorThumbnailSubsystem unavailable: %s" % e)
        return False

    try:
        rt = ets.render_thumbnail(asset, size, size)
    except Exception as e:
        unreal.log_warning("[FXLibrary] render_thumbnail failed: %s" % e)
        return False

    if rt is None:
        return False
    return _rt_to_png(rt, out_path)


# ---------------------------------------------------------------------------
# Playing-frame capture (spawn + simulate + SceneCapture2D)
# ---------------------------------------------------------------------------

def _editor_world():
    try:
        return unreal.EditorLevelLibrary.get_editor_world()
    except Exception:
        try:
            sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
            return sub.get_editor_world()
        except Exception:
            return None


def _spawn_system(world, asset):
    """Spawn a Niagara or Cascade system at the origin. Returns the component
    (NiagaraComponent / ParticleSystemComponent) or None."""
    loc = unreal.Vector(0.0, 0.0, 0.0)
    rot = unreal.Rotator(0.0, 0.0, 0.0)
    scl = unreal.Vector(1.0, 1.0, 1.0)
    cls = None
    try:
        cls = asset.get_class().get_name()
    except Exception:
        cls = None

    if cls == "NiagaraSystem" or isinstance(asset, unreal.NiagaraSystem):
        try:
            return unreal.NiagaraFunctionLibrary.spawn_system_at_location(
                world, asset, loc, rot, scl, False)
        except Exception as e:
            unreal.log_warning("[FXLibrary] spawn Niagara failed: %s" % e)
    if cls == "ParticleSystem" or isinstance(asset, unreal.ParticleSystem):
        try:
            return unreal.GameplayStatics.spawn_emitter_at_location(
                world, asset, loc, rot, scl, False)
        except Exception as e:
            unreal.log_warning("[FXLibrary] spawn Cascade failed: %s" % e)
    return None


def _advance_simulation(comp, seconds):
    """Best-effort: start the system and try to advance the simulation. The
    headless world does not tick during a blocking python script, so this is
    best-effort; if it cannot advance, the capture still happens at the emission
    start frame. A live editor with play-in-editor gives the truest play."""
    try:
        comp.activate(True)
    except Exception:
        pass
    steps = max(1, int(round(seconds * 30.0)))
    dt = 1.0 / 30.0
    for fn_name in ("tick", "component_tick", "TickComponent"):
        fn = getattr(comp, fn_name, None)
        if fn is None:
            continue
        advanced = False
        for _ in range(steps):
            try:
                try:
                    fn(dt)
                    advanced = True
                except TypeError:
                    fn(dt, None)
                    advanced = True
            except Exception:
                break
        if advanced:
            return


def _make_render_target(size):
    try:
        rt = unreal.RenderTarget2D()
        rt.set_editor_property("size_x", size)
        rt.set_editor_property("size_y", size)
        try:
            rt.render_target_format = unreal.RenderTargetFormat.RTF_RGBA8
        except Exception:
            pass
        return rt
    except Exception as e:
        unreal.log_warning("[FXLibrary] create RenderTarget failed: %s" % e)
        return None


def _destroy_actor(actor):
    try:
        actor.destroy_actor()
    except Exception:
        pass


def _scene_capture(comp, size, distance):
    """Place a SceneCapture2D in front of the effect, aimed at it, and capture a
    frame into a render target. Returns the render target or None."""
    try:
        comp_loc = comp.get_world_location()
    except Exception:
        comp_loc = unreal.Vector(0.0, 0.0, 0.0)
    cam_loc = unreal.Vector(comp_loc.x - distance, comp_loc.y, comp_loc.z + 60.0)
    try:
        rot = unreal.MathLibrary.find_look_at_rotation(cam_loc, comp_loc)
    except Exception:
        rot = unreal.Rotator(0.0, 90.0, 0.0)
    try:
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.SceneCapture2D, cam_loc, rot)
    except Exception as e:
        unreal.log_warning("[FXLibrary] spawn SceneCapture2D failed: %s" % e)
        return None
    if actor is None:
        return None
    cap = actor.get_component_by_class(unreal.SceneCaptureComponent2D)
    if cap is None:
        _destroy_actor(actor)
        return None
    rt = _make_render_target(size)
    if rt is None:
        _destroy_actor(actor)
        return None
    cap.texture_target = rt
    try:
        cap.capture_source = unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR
    except Exception:
        pass
    try:
        cap.capture_scene()
    except Exception as e:
        unreal.log_warning("[FXLibrary] capture_scene failed: %s" % e)
    return rt


def try_render_playing(asset, out_path, size=256, seconds=0.6, distance=350.0):
    """Best-effort: capture a frame of the effect *actually playing*. Spawns the
    system, advances it, and grabs a SceneCapture2D frame.

    Headless UE does not tick the world during a blocking Python script, so a
    "true" playing frame is rarely obtainable. To guarantee the user gets at
    least *some* usable image, we first render the engine's static editor
    thumbnail (which already simulates Niagara) and only then attempt the
    playing-frame capture. If the capture succeeds it overwrites the static
    thumbnail; otherwise the static thumbnail remains as a fallback."""
    # Baseline: always produce a static editor thumbnail first. This is the
    # reliable path and prevents the common "0/1 available" result.
    static_ok = try_render(asset, out_path, size)

    playing_ok = False
    try:
        world = _editor_world()
        if world is None:
            raise RuntimeError("no editor world")
        comp = _spawn_system(world, asset)
        if comp is None:
            raise RuntimeError("could not spawn FX system")
        owner = None
        try:
            owner = comp.get_owner()
        except Exception:
            owner = None
        try:
            _advance_simulation(comp, seconds)
            rt = _scene_capture(comp, size, distance)
        finally:
            # Clean up the spawned actor (component is owned by it).
            if owner is not None:
                _destroy_actor(owner)
            else:
                try:
                    comp.destroy_component(comp)
                except Exception:
                    pass
        if rt is not None and _rt_to_png(rt, out_path):
            playing_ok = True
    except Exception as e:
        unreal.log_warning("[FXLibrary] playing capture failed: %s" % e)

    if playing_ok:
        unreal.log("[FXLibrary] playing capture succeeded for %s" % asset.get_name())
    elif static_ok:
        unreal.log_warning("[FXLibrary] playing capture unavailable -> using static thumbnail")
    else:
        unreal.log_warning("[FXLibrary] both playing capture and static thumbnail failed")
    return playing_ok or static_ok


def run_thumbnail_batch(params):
    """params: {"outDir": str, "objectPaths": [str] (optional), "size": int (optional)}
    -> data: {"thumbnails": [{"objectPath","available","path"}], "count": N}"""
    out_dir = params.get("outDir")
    if not out_dir:
        raise RuntimeError("thumbnail_batch requires 'outDir'")
    fx_common.ensure_dir(out_dir)
    size = int(params.get("size", 256))

    object_paths = params.get("objectPaths")
    if not object_paths:
        fx_common.try_scan()
        object_paths = [fx_common.asset_data_object_path(a) for a in fx_common.get_all_fx_asset_data()]

    results = []
    for op in object_paths:
        asset = unreal.EditorAssetLibrary.load_asset(op)
        if asset is None:
            unreal.log_warning("[FXLibrary] thumbnail: cannot load %s" % op)
            results.append({"objectPath": op, "available": False, "path": None})
            continue
        out_path = os.path.join(out_dir, asset.get_name() + ".png")
        ok = try_render(asset, out_path, size)
        results.append({"objectPath": op, "available": ok, "path": out_path if ok else None})
    return {"thumbnails": results, "count": len(results)}
