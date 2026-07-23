"""
Extract equations, custom properties, and dimensions from a SolidWorks part.
Usage: python extract_full.py "C:\\path\\part.SLDPRT"
"""
import sys
import json
import os
import win32com.client

swDocPART = 1

def extract(sldprt_path):
    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True
    model = sw.OpenDoc(sldprt_path, swDocPART)
    if model is None:
        print(f"ERROR: Cannot open {sldprt_path}")
        return

    result = {
        "part_name": model.GetTitle,
        "sldprt_path": sldprt_path,
        "equations": [],
        "custom_properties": {},
        "dimensions": {}
    }

    # 1. Equations
    try:
        eq_mgr = model.GetEquationMgr
        count = eq_mgr.GetCount
        print(f"=== Equations ({count}) ===")
        for i in range(count):
            eq = eq_mgr.Equation(i)
            value = eq_mgr.Value(i)
            global_eq = eq_mgr.GlobalVariable(i)
            result["equations"].append({
                "index": i,
                "equation": eq,
                "value": value,
                "is_global_variable": bool(global_eq)
            })
            print(f"  [{i}] {eq}  =>  {value}")
    except Exception as e:
        print(f"Equations error: {e}")

    # 2. Custom properties (备注/自定义属性)
    try:
        cpm = model.Extension.CustomPropertyManager("")
        names = cpm.GetNames
        if names:
            print(f"\n=== Custom Properties ({len(names)}) ===")
            for name in names:
                try:
                    val = cpm.Get(name)
                except Exception:
                    try:
                        # Get3 returns (val, resolved_val)
                        val, _ = cpm.Get3(name, False)
                    except Exception:
                        try:
                            val = cpm.Get4(name, False)
                            val = val[0] if isinstance(val, (list, tuple)) else str(val)
                        except Exception as e3:
                            val = f"(error: {e3})"
                result["custom_properties"][name] = val
                print(f"  {name} = {val}")
        else:
            print("\n=== Custom Properties (0) ===")
            # Fallback: try using the model's CustomInfo2 / CustomInfo
            try:
                cfg_names = ["Default", ""]
                for cfg in cfg_names:
                    try:
                        info_names = model.CustomInfoNames(cfg) if hasattr(model, 'CustomInfoNames') else None
                    except:
                        info_names = None
                    if info_names:
                        print(f"  (via model, cfg='{cfg}')")
                        for n in info_names:
                            v = model.CustomInfo2(cfg, n)
                            result["custom_properties"][n] = v
                            print(f"  {n} = {v}")
                        break
            except Exception as e2:
                print(f"  Fallback error: {e2}")
    except Exception as e:
        print(f"Custom properties error: {e}")

    # 3. Dimensions (traverse feature tree)
    try:
        feat = model.FirstFeature
        dim_count = 0
        while feat is not None:
            dim_count = _collect_dims(feat, result["dimensions"], dim_count)
            sub = feat.GetFirstSubFeature
            while sub is not None:
                dim_count = _collect_dims(sub, result["dimensions"], dim_count)
                sub = sub.GetNextSubFeature
            feat = feat.GetNextFeature
        print(f"\n=== Dimensions ({dim_count}) ===")
    except Exception as e:
        print(f"Dimensions error: {e}")

    # Save JSON
    out_path = sldprt_path.replace(".SLDPRT", "_full.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSaved -> {out_path}")


def _collect_dims(feat, dims_dict, count):
    try:
        disp_dim = feat.GetFirstDisplayDimension
    except:
        return count
    while disp_dim is not None:
        try:
            dim = disp_dim.GetDimension2(0, 0)
            if dim is not None:
                name = dim.FullName
                value_mm = round(dim.SystemValue * 1000, 4)
                # Also get dimension type: 1=angle(rad), 0=linear
                try:
                    dim_type = dim.Type2
                except:
                    dim_type = None
                dims_dict[name] = {
                    "value": value_mm,
                    "type": dim_type,
                    "label": ""
                }
                count += 1
        except:
            try:
                dim = disp_dim.GetDimension
                if dim is not None:
                    name = dim.FullName
                    value_mm = round(dim.SystemValue * 1000, 4)
                    dims_dict[name] = {"value": value_mm, "type": None, "label": ""}
                    count += 1
            except:
                pass
        try:
            disp_dim = feat.GetNextDisplayDimension(disp_dim)
        except:
            break
    return count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    extract(sys.argv[1])
