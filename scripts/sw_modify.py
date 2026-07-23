"""
SolidWorks parameter modifier - called by Hermes via terminal.

Usage:
    python sw_modify.py <SLDPRT_PATH> <PARAM=VAL> [PARAM=VAL...] [options]

Options:
    --step <OUTPUT>        Export STEP after modification
    --save-as <PATH>       Save modified part as a new SLDPRT (original unchanged)
    --list                 List all parameters and equations
    --rollback             Restore to baseline snapshot
    --new-snapshot         Save current state as new baseline
    --batch <JSON_FILE>    Batch modify: read variants from JSON, output multiple files

Examples:
    # Modify and overwrite original
    python sw_modify.py "C:\\parts\\part.SLDPRT" "L=120" --step "C:\\output\\mod.STEP"

    # Modify and save as new file (original unchanged)
    python sw_modify.py "C:\\parts\\part.SLDPRT" "L=120" --save-as "C:\\output\\part-L120.SLDPRT" --step "C:\\output\\part-L120.STEP"

    # Batch: generate multiple variants from a JSON config
    python sw_modify.py "C:\\parts\\part.SLDPRT" --batch "C:\\parts\\batch_config.json"
"""
import sys
import os
import json
import time
import win32com.client

# SolidWorks constants
swDocPART = 1
swOpenDocOptions_Silent = 1

# Snapshot directory (next to the SLDPRT)
SNAPSHOT_DIRNAME = ".sw_snapshots"


def _snapshot_path(sldprt_path):
    """Return the snapshot file path for a given SLDPRT."""
    d = os.path.dirname(sldprt_path)
    name = os.path.splitext(os.path.basename(sldprt_path))[0]
    snap_dir = os.path.join(d, SNAPSHOT_DIRNAME)
    os.makedirs(snap_dir, exist_ok=True)
    return os.path.join(snap_dir, f"{name}_last.json")


def _save_snapshot(model, sldprt_path):
    """Save current equation values + dimension values to a JSON snapshot."""
    snapshot = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sldprt_path": sldprt_path,
        "equations": {},
        "dimensions": {}
    }

    # Save equations
    try:
        eq_mgr = model.GetEquationMgr
        for i in range(eq_mgr.GetCount):
            eq_str = eq_mgr.Equation(i)
            val = eq_mgr.Value(i)
            is_gv = eq_mgr.GlobalVariable(i)
            snapshot["equations"][str(i)] = {
                "equation": eq_str,
                "value": val,
                "is_global": bool(is_gv)
            }
    except Exception:
        pass

    # Save dimensions (traverse feature tree)
    feat = model.FirstFeature
    while feat is not None:
        _collect_dim_values(feat, snapshot["dimensions"])
        sub = feat.GetFirstSubFeature
        while sub is not None:
            _collect_dim_values(sub, snapshot["dimensions"])
            sub = sub.GetNextSubFeature
        feat = feat.GetNextFeature

    path = _snapshot_path(sldprt_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    print(f"Snapshot saved: {path}")
    return snapshot


def _collect_dim_values(feat, dims_dict):
    """Collect dimension full_name -> value from a feature."""
    try:
        disp_dim = feat.GetFirstDisplayDimension
    except Exception:
        return
    while disp_dim is not None:
        try:
            dim = disp_dim.GetDimension2(0, 0)
            if dim is not None:
                full_name = dim.FullName
                value_mm = round(dim.SystemValue * 1000, 6)
                dims_dict[full_name] = value_mm
        except Exception:
            try:
                dim = disp_dim.GetDimension
                if dim is not None:
                    full_name = dim.FullName
                    value_mm = round(dim.SystemValue * 1000, 6)
                    dims_dict[full_name] = value_mm
            except:
                pass
        try:
            disp_dim = feat.GetNextDisplayDimension(disp_dim)
        except Exception:
            break


def rollback(sw, sldprt_path, step_output=None):
    """Restore parameters from the last snapshot."""
    snap_path = _snapshot_path(sldprt_path)
    if not os.path.exists(snap_path):
        print(f"ERROR: No snapshot found at {snap_path}")
        print("Nothing to rollback.")
        return

    with open(snap_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    print(f"Rolling back to snapshot: {snapshot['timestamp']}")

    model = _open_model(sw, sldprt_path)
    eq_mgr = model.GetEquationMgr

    # Restore equations
    restored_eq = 0
    for idx_str, info in snapshot.get("equations", {}).items():
        idx = int(idx_str)
        eq_str = info["equation"]
        try:
            current_eq = eq_mgr.Equation(idx)
            if current_eq != eq_str:
                eq_mgr.Equation(idx, eq_str)
                restored_eq += 1
        except Exception as e:
            print(f"  Equation {idx}: ERROR - {e}")

    # Restore dimensions
    restored_dim = 0
    for full_name, value_mm in snapshot.get("dimensions", {}).items():
        try:
            param = model.Parameter(full_name)
            if param is not None:
                current = round(param.SystemValue * 1000, 6)
                if abs(current - value_mm) > 0.0001:
                    param.SystemValue = value_mm / 1000.0
                    restored_dim += 1
        except Exception:
            pass

    model.EditRebuild3
    print(f"Rebuilt. Restored {restored_eq} equations, {restored_dim} dimensions.")

    # Save
    try:
        model.Save3(0, None, None)
    except Exception:
        try:
            model.Save3(0)
        except Exception:
            try:
                model.Save2(False)
            except Exception:
                model.Save
    print("Saved SLDPRT.")

    if step_output:
        out_dir = os.path.dirname(step_output)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        try:
            success = model.SaveAs(step_output)
        except Exception:
            try:
                success = model.SaveAs4(step_output, 0, 1, None)
            except Exception:
                success = False
        if success:
            print(f"Exported STEP: {step_output}")
        else:
            print("STEP export FAILED")

    # Show current equation values
    try:
        print("\n--- 回退后方程式 ---")
        for i in range(eq_mgr.GetCount):
            eq = eq_mgr.Equation(i)
            val = eq_mgr.Value(i)
            print(f"  {eq}  =>  {val}")
    except:
        pass

    print("Rollback complete.")


def _open_model(sw, sldprt_path):
    """Open a SLDPRT and return the model object."""
    model = sw.OpenDoc(sldprt_path, swDocPART)
    if model is None:
        try:
            model = sw.OpenDoc5(sldprt_path, swDocPART, swOpenDocOptions_Silent, "", 0)
        except Exception as e:
            print(f"ERROR: Cannot open {sldprt_path}: {e}")
            sys.exit(1)
    try:
        sw.ActivateDoc(sldprt_path)
    except Exception:
        pass
    return model


def _get_equation_names(model):
    """Return set of global variable names from equation manager."""
    names = set()
    try:
        eq_mgr = model.GetEquationMgr
        count = eq_mgr.GetCount
        for i in range(count):
            eq = eq_mgr.Equation(i)
            if eq_mgr.GlobalVariable(i):
                name = eq.split("=")[0].strip().strip('"').strip("'")
                names.add(name)
    except Exception:
        pass
    return names


def _build_dim_name_map(model):
    """Build a map of short names -> full dimension names for fuzzy matching."""
    dim_map = {}
    feat = model.FirstFeature
    while feat is not None:
        _collect_dim_names(feat, dim_map)
        sub = feat.GetFirstSubFeature
        while sub is not None:
            _collect_dim_names(sub, dim_map)
            sub = sub.GetNextSubFeature
        feat = feat.GetNextFeature
    return dim_map


def _collect_dim_names(feat, dim_map):
    """Collect dimension short names -> full names from a feature."""
    try:
        disp_dim = feat.GetFirstDisplayDimension
    except Exception:
        return
    while disp_dim is not None:
        try:
            dim = disp_dim.GetDimension2(0, 0)
            if dim is not None:
                full_name = dim.FullName
                parts = full_name.split("@")
                if len(parts) >= 2:
                    short = f"{parts[0]}@{parts[1]}"
                    if short not in dim_map:
                        dim_map[short] = full_name
                    first = parts[0]
                    if first not in dim_map:
                        dim_map[first] = full_name
        except Exception:
            try:
                dim = disp_dim.GetDimension
                if dim is not None:
                    full_name = dim.FullName
                    parts = full_name.split("@")
                    if len(parts) >= 2:
                        short = f"{parts[0]}@{parts[1]}"
                        if short not in dim_map:
                            dim_map[short] = full_name
                        first = parts[0]
                        if first not in dim_map:
                            dim_map[first] = full_name
            except:
                pass
        try:
            disp_dim = feat.GetNextDisplayDimension(disp_dim)
        except Exception:
            break


def list_params(model):
    """Print all equations and dimensions."""
    try:
        eq_mgr = model.GetEquationMgr
        count = eq_mgr.GetCount
        if count > 0:
            print(f"=== Equations ({count}) ===")
            for i in range(count):
                eq = eq_mgr.Equation(i)
                val = eq_mgr.Value(i)
                gv = " [全局变量]" if eq_mgr.GlobalVariable(i) else " [尺寸链接]"
                print(f"  [{i}] {eq}  =>  {val}{gv}")
            print()
    except Exception as e:
        print(f"Equations error: {e}")

    feat = model.FirstFeature
    count = 0
    while feat is not None:
        count = _print_dims(feat, count)
        sub = feat.GetFirstSubFeature
        while sub is not None:
            count = _print_dims(sub, count)
            sub = sub.GetNextSubFeature
        feat = feat.GetNextFeature
    print(f"\nTotal dimensions: {count}")


def _print_dims(feat, count):
    try:
        disp_dim = feat.GetFirstDisplayDimension
    except Exception:
        return count
    while disp_dim is not None:
        try:
            dim = disp_dim.GetDimension2(0, 0)
            if dim is not None:
                name = dim.FullName
                value_mm = dim.SystemValue * 1000
                print(f"  {name} = {value_mm:.2f} mm")
                count += 1
        except Exception:
            try:
                dim = disp_dim.GetDimension
                if dim is not None:
                    name = dim.FullName
                    value_mm = dim.SystemValue * 1000
                    print(f"  {name} = {value_mm:.2f} mm")
                    count += 1
            except Exception:
                pass
        try:
            disp_dim = feat.GetNextDisplayDimension(disp_dim)
        except Exception:
            break
    return count


def batch_modify(sw, sldprt_path, batch_json_path):
    """Batch modify: read variants from JSON, save each as a new SLDPRT + STEP.
    
    JSON format:
    [
        {
            "name": "variant-1",
            "changes": {"L": 120, "N1": 3},
            "step": true
        },
        {
            "name": "variant-2",
            "changes": {"L": 100, "N1": 7},
            "step": true
        }
    ]
    
    Output files go to <sldprt_dir>/output/<name>.SLDPRT and .STEP
    """
    with open(batch_json_path, "r", encoding="utf-8") as f:
        variants = json.load(f)
    
    if not isinstance(variants, list):
        print("ERROR: Batch JSON must be a list of variant objects.")
        return
    
    base_dir = os.path.dirname(sldprt_path)
    out_dir = os.path.join(base_dir, "output")
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Batch mode: {len(variants)} variants")
    print(f"Output directory: {out_dir}\n")
    
    results = []
    
    for idx, variant in enumerate(variants):
        name = variant.get("name", f"variant-{idx+1}")
        changes = variant.get("changes", {})
        export_step = variant.get("step", True)
        
        print(f"{'='*50}")
        print(f"[{idx+1}/{len(variants)}] {name}")
        print(f"  Changes: {changes}")
        
        save_as_path = os.path.join(out_dir, f"{name}.SLDPRT")
        step_path = os.path.join(out_dir, f"{name}.STEP") if export_step else None
        
        # Close any open documents first to avoid conflicts
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        
        try:
            modify_and_export(sw, sldprt_path, changes, step_path, save_as_path)
            results.append({"name": name, "status": "OK", "sldprt": save_as_path, "step": step_path})
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"name": name, "status": f"ERROR: {e}"})
        
        print()
    
    # Summary
    print(f"{'='*50}")
    print("Batch summary:")
    for r in results:
        status_icon = "✅" if r["status"] == "OK" else "❌"
        print(f"  {status_icon} {r['name']}: {r['status']}")


def modify_and_export(sw, sldprt_path, changes, step_output=None, save_as=None):
    """Modify dimensions/equations, rebuild, optionally export STEP / save as new SLDPRT.
    
    If save_as is specified, the modified part is saved as a new SLDPRT file
    and the original file is left unchanged.
    """
    model = _open_model(sw, sldprt_path)
    title = model.GetTitle
    print(f"Opened: {title}")

    # --- Save snapshot BEFORE any modification (only if no snapshot exists yet) ---
    snap_path = _snapshot_path(sldprt_path)
    if not os.path.exists(snap_path):
        _save_snapshot(model, sldprt_path)
        print("（首次修改，已保存原始快照）")
    else:
        print(f"（快照已存在，保留原始状态）")

    # Get equation global variable names for smart routing
    eq_names = _get_equation_names(model)
    eq_mgr = model.GetEquationMgr

    # Build a map of short dimension names -> full names for fuzzy matching
    dim_map = _build_dim_name_map(model)

    for param_name, new_val_mm in changes.items():
        # 1) Check if this is an equation global variable
        if param_name in eq_names:
            try:
                found = False
                for i in range(eq_mgr.GetCount):
                    eq = eq_mgr.Equation(i)
                    if eq_mgr.GlobalVariable(i):
                        var_name = eq.split("=")[0].strip().strip('"').strip("'")
                        if var_name == param_name:
                            old_val = eq_mgr.Value(i)
                            # Preserve comment: everything after the first single quote
                            comment = ""
                            if "'" in eq:
                                comment = "'" + eq.split("'", 1)[1]
                            new_eq_str = f'"{param_name}" = {new_val_mm}{comment}'
                            eq_mgr.Equation(i, new_eq_str)
                            print(f"  [方程式] {param_name}: {old_val} -> {new_val_mm}  {comment}")
                            found = True
                            break
                if not found:
                    eq_idx = eq_mgr.Add2(f'"{param_name}" = {new_val_mm}', 1, 0)
                    print(f"  [方程式] {param_name}: (new) = {new_val_mm}")
            except Exception as e:
                print(f"  [方程式] {param_name}: ERROR - {e}")
        # 2) Try exact dimension name match
        elif model.Parameter(param_name) is not None:
            try:
                param = model.Parameter(param_name)
                old_val = param.SystemValue * 1000
                param.SystemValue = new_val_mm / 1000.0
                print(f"  {param_name}: {old_val:.1f} -> {new_val_mm} mm")
            except Exception as e:
                print(f"  {param_name}: ERROR - {e}")
        # 3) Try fuzzy match (e.g. "L" -> "L@凸台-拉伸1@...Part")
        elif param_name in dim_map:
            full_name = dim_map[param_name]
            try:
                param = model.Parameter(full_name)
                old_val = param.SystemValue * 1000
                param.SystemValue = new_val_mm / 1000.0
                print(f"  {full_name}: {old_val:.1f} -> {new_val_mm} mm")
            except Exception as e:
                print(f"  {full_name}: ERROR - {e}")
        else:
            print(f"  {param_name}: NOT FOUND - skipped")

    model.EditRebuild3
    print("Rebuilt.")

    # Show equation values after rebuild
    try:
        print("\n--- 方程式更新后 ---")
        for i in range(eq_mgr.GetCount):
            eq = eq_mgr.Equation(i)
            val = eq_mgr.Value(i)
            print(f"  {eq}  =>  {val}")
    except:
        pass

    # Save: either as new file or overwrite original
    if save_as:
        # Save as new SLDPRT - original file stays unchanged
        out_dir = os.path.dirname(save_as)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        try:
            success = model.SaveAs(save_as)
        except Exception:
            try:
                success = model.SaveAs4(save_as, 0, 0, None)
            except Exception as e:
                print(f"SaveAs error: {e}")
                success = False
        if success:
            print(f"Saved new SLDPRT: {save_as}")
        else:
            print("SaveAs FAILED")
    else:
        # Overwrite original
        try:
            model.Save3(0, None, None)
        except Exception:
            try:
                model.Save3(0)
            except Exception:
                try:
                    model.Save2(False)
                except Exception:
                    model.Save
        print("Saved SLDPRT.")

    if step_output:
        out_dir = os.path.dirname(step_output)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        try:
            success = model.SaveAs(step_output)
        except Exception:
            try:
                success = model.SaveAs4(step_output, 0, 1, None)
            except Exception:
                success = False
        if success:
            print(f"Exported STEP: {step_output}")
        else:
            print("STEP export FAILED")

    print("Done.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    sldprt_path = args[0]
    changes = {}
    step_output = None
    save_as = None
    batch_file = None
    list_only = False
    do_rollback = False
    new_snapshot = False

    i = 1
    while i < len(args):
        if args[i] == "--step":
            step_output = args[i + 1]
            i += 2
        elif args[i] == "--save-as":
            save_as = args[i + 1]
            i += 2
        elif args[i] == "--batch":
            batch_file = args[i + 1]
            i += 2
        elif args[i] == "--list":
            list_only = True
            i += 1
        elif args[i] == "--rollback":
            do_rollback = True
            i += 1
        elif args[i] == "--new-snapshot":
            new_snapshot = True
            i += 1
        elif "=" in args[i]:
            k, v = args[i].split("=", 1)
            changes[k] = float(v)
            i += 1
        else:
            i += 1

    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True

    if new_snapshot:
        model = _open_model(sw, sldprt_path)
        _save_snapshot(model, sldprt_path)
        print("New snapshot saved as baseline.")
    elif do_rollback:
        rollback(sw, sldprt_path, step_output)
    elif list_only:
        model = _open_model(sw, sldprt_path)
        print(f"Parameters of {model.GetTitle}:")
        list_params(model)
    elif batch_file:
        batch_modify(sw, sldprt_path, batch_file)
    elif changes:
        modify_and_export(sw, sldprt_path, changes, step_output, save_as)
    else:
        print("No changes, --list, --rollback, --new-snapshot, or --batch specified.")
