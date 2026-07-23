"""
SolidWorks parameter modifier - called by Hermes via terminal.

Usage:
    python sw_modify.py <SLDPRT_PATH> <PARAM=VAL> [PARAM=VAL...] [--step <OUTPUT>] [--list]

Examples:
    # Modify dimension
    python sw_modify.py "C:\\parts\\part.SLDPRT" "D1@Sketch1=60" --step "C:\\output\\modified.STEP"

    # Modify equation global variable (e.g. total length L)
    python sw_modify.py "C:\\parts\\part.SLDPRT" "L=120" --step "C:\\output\\modified.STEP"

    # List all parameters and equations
    python sw_modify.py "C:\\parts\\part.SLDPRT" --list
"""
import sys
import os
import json
import win32com.client

# SolidWorks constants
swDocPART = 1
swOpenDocOptions_Silent = 1


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
            # Global variable format: "VarName" = value'comment
            # Dimension link format: "D1@Feature" = "VarName"
            if eq_mgr.GlobalVariable(i):
                # Extract variable name from equation string
                # e.g. '"A"= 20\'胶面边距A' -> A
                name = eq.split("=")[0].strip().strip('"').strip("'")
                names.add(name)
    except Exception:
        pass
    return names


def _build_dim_name_map(model):
    """Build a map of short names -> full dimension names for fuzzy matching.
    
    e.g. "L" -> "L@凸台-拉伸1@MyPart.Part"
         "D1@草图1" -> "D1@草图1@MyPart.Part"
    """
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
                # full_name format: "D1@草图1@PartName.Part"
                # Split by @ and take first 1-2 segments as short name
                parts = full_name.split("@")
                if len(parts) >= 2:
                    # Short name: "D1@草图1"
                    short = f"{parts[0]}@{parts[1]}"
                    if short not in dim_map:
                        dim_map[short] = full_name
                    # Also map just the first segment if unique
                    # e.g. "L" -> "L@凸台-拉伸1@..."
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
    # Equations first
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

    # Dimensions
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


def modify_and_export(sw, sldprt_path, changes, step_output=None):
    """Modify dimensions/equations, rebuild, optionally export STEP."""
    model = _open_model(sw, sldprt_path)
    title = model.GetTitle
    print(f"Opened: {title}")

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
                            new_eq_str = f'"{param_name}" = {new_val_mm}'
                            eq_mgr.Equation(i, new_eq_str)
                            print(f"  [方程式] {param_name}: {old_val} -> {new_val_mm}")
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

    # Save SLDPRT
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
        # Export STEP via SaveAs - pywin32 dynamic dispatch needs simpler call
        try:
            success = model.SaveAs(step_output)
        except Exception as e:
            try:
                # Try with more params: SaveAs(filename, version, options, exportData)
                success = model.SaveAs4(step_output, 0, 1, None)
            except Exception as e2:
                print(f"STEP export error: {e2}")
                success = False
        if success:
            print(f"Exported STEP: {step_output}")
        else:
            print(f"STEP export FAILED")

    print("Done.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    sldprt_path = args[0]
    changes = {}
    step_output = None
    list_only = False

    i = 1
    while i < len(args):
        if args[i] == "--step":
            step_output = args[i + 1]
            i += 2
        elif args[i] == "--list":
            list_only = True
            i += 1
        elif "=" in args[i]:
            k, v = args[i].split("=", 1)
            changes[k] = float(v)
            i += 1
        else:
            i += 1

    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True

    if list_only:
        model = _open_model(sw, sldprt_path)
        print(f"Parameters of {model.GetTitle}:")
        list_params(model)
    elif changes:
        modify_and_export(sw, sldprt_path, changes, step_output)
    else:
        print("No changes or --list specified.")
