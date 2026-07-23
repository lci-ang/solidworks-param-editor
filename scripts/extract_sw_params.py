"""
SolidWorks parameter extractor — run once per part.

Usage:
    python extract_sw_params.py "C:\parts\FD7111503.SLDPRT"
    
Outputs: params.json in the same directory as the SLDPRT.
"""
import sys
import json
import os
import win32com.client

def extract(sldprt_path):
    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True
    
    doc = sw.OpenDoc(sldprt_path, 1)
    if not doc:
        print(f"ERROR: Cannot open {sldprt_path}")
        return
    
    model = sw.ActiveDoc
    print(f"Extracting parameters from: {model.GetTitle()}")
    
    dims = model.Extension.GetDimensions()
    
    params = {}
    for dim_name in dims:
        try:
            value_mm = round(model.Parameter(dim_name).SystemValue * 1000, 4)
            params[dim_name] = {"value": value_mm, "label": ""}
        except Exception as e:
            params[dim_name] = {"value": None, "label": "", "error": str(e)}
    
    out = {
        "part_name": model.GetTitle().replace(".SLDPRT", ""),
        "sldprt_path": sldprt_path,
        "output_dir": os.path.join(os.path.dirname(sldprt_path), "output"),
        "parameters": params
    }
    
    out_path = sldprt_path.replace(".SLDPRT", "_params.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    
    print(f"\n{len(params)} parameters → {out_path}")
    for name, info in params.items():
        v = info.get("value")
        err = info.get("error", "")
        if v is not None:
            print(f"  {name} = {v} mm")
        else:
            print(f"  {name} = ERROR: {err}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    extract(sys.argv[1])
