"""
SolidWorks parameter extractor - run once per part.

Usage:
    python extract_sw_params.py "C:\\parts\\part.SLDPRT"
    
Outputs: <partname>_params.json in the same directory as the SLDPRT.
"""
import sys
import json
import os
import win32com.client

# SolidWorks doc types
swDocPART = 1
swDocASSEMBLY = 2
swDocDRAWING = 3

# OpenDoc options
swOpenDocOptions_Silent = 1

def extract(sldprt_path):
    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True
    
    # Use OpenDoc (simpler, no ByRef params that break pywin32 dynamic dispatch)
    # Don't rely on sw.ActiveDoc because SW might already have another file open
    model = sw.OpenDoc(sldprt_path, swDocPART)
    if model is None:
        # Fallback: try OpenDoc5
        try:
            model = sw.OpenDoc5(sldprt_path, swDocPART, swOpenDocOptions_Silent, "", 0)
        except Exception as e:
            print(f"ERROR: Cannot open {sldprt_path}: {e}")
            return
    
    # Activate the document so feature traversal works reliably
    try:
        sw.ActivateDoc(sldprt_path)
    except Exception:
        pass  # might already be active
    
    title = model.GetTitle
    print(f"Extracting parameters from: {title}")
    
    params = {}
    
    # Traverse the feature tree to find all dimensions
    feat = model.FirstFeature
    while feat is not None:
        _collect_dims_from_feature(feat, params)
        # Also check sub-features (e.g. sketches under extrudes)
        sub_feat = feat.GetFirstSubFeature
        while sub_feat is not None:
            _collect_dims_from_feature(sub_feat, params)
            sub_feat = sub_feat.GetNextSubFeature
        feat = feat.GetNextFeature
    
    out = {
        "part_name": title.replace(".SLDPRT", "").replace(".SLDPRT", ""),
        "sldprt_path": sldprt_path,
        "output_dir": os.path.join(os.path.dirname(sldprt_path), "output"),
        "parameters": params
    }
    
    out_path = sldprt_path.replace(".SLDPRT", "_params.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    
    print(f"\n{len(params)} parameters -> {out_path}")
    for name, info in params.items():
        v = info.get("value")
        err = info.get("error", "")
        if v is not None:
            print(f"  {name} = {v} mm")
        else:
            print(f"  {name} = ERROR: {err}")

def _collect_dims_from_feature(feat, params):
    """Collect all display dimensions from a feature."""
    try:
        disp_dim = feat.GetFirstDisplayDimension
    except Exception:
        return
    while disp_dim is not None:
        try:
            # GetDimension2(0,0) is the modern API
            dim = disp_dim.GetDimension2(0, 0)
            if dim is not None:
                name = dim.FullName
                value_mm = round(dim.SystemValue * 1000, 4)
                params[name] = {"value": value_mm, "label": ""}
        except Exception:
            try:
                dim = disp_dim.GetDimension
                if dim is not None:
                    name = dim.FullName
                    value_mm = round(dim.SystemValue * 1000, 4)
                    params[name] = {"value": value_mm, "label": ""}
            except Exception:
                pass
        try:
            disp_dim = feat.GetNextDisplayDimension(disp_dim)
        except Exception:
            break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    extract(sys.argv[1])
