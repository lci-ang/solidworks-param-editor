"""
SolidWorks parameter modifier — called by Hermes via terminal.

Usage:
    python sw_modify.py <SLDPRT_PATH> <PARAM=VAL> [PARAM=VAL...] [--step <OUTPUT>] [--list]

Examples:
    python sw_modify.py "C:\parts\FD7111503.SLDPRT" "D1@Sketch1=60" "D1@Hole1=1.5" --step "C:\output\modified.STEP"
    python sw_modify.py "C:\parts\FD7111503.SLDPRT" --list
"""
import sys
import win32com.client

def list_params(model):
    dims = model.Extension.GetDimensions()
    for d in dims:
        v = model.Parameter(d).SystemValue
        print(f"  {d} = {v * 1000:.2f} mm")

def modify_and_export(sldprt_path, changes, step_output=None):
    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True
    
    doc = sw.OpenDoc(sldprt_path, 1)
    if not doc:
        print(f"ERROR: Cannot open {sldprt_path}")
        sys.exit(1)
    
    model = sw.ActiveDoc
    print(f"Opened: {model.GetTitle()}")
    
    for param_name, new_val_mm in changes.items():
        old_val = model.Parameter(param_name).SystemValue * 1000
        model.Parameter(param_name).SystemValue = new_val_mm / 1000.0
        print(f"  {param_name}: {old_val:.1f} → {new_val_mm} mm")
    
    model.EditRebuild3()
    print("Rebuilt.")
    
    if step_output:
        model.SaveAs(step_output)
        print(f"Exported: {step_output}")
    
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
    doc = sw.OpenDoc(sldprt_path, 1)
    model = sw.ActiveDoc
    
    if list_only:
        print(f"Parameters of {model.GetTitle()}:")
        list_params(model)
    elif changes:
        sw.CloseDoc(model.GetTitle())
        modify_and_export(sldprt_path, changes, step_output)
    else:
        print("No changes or --list specified.")
