#!/usr/bin/env python3
import json
import os
import re
import sys

def parse_cpuinfo():
    if not os.path.exists("/proc/cpuinfo"):
        return None
    
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception:
        return None

    blocks = [b for b in raw.split("\n\n") if b]
    if not blocks:
        return None
    
    first_proc = blocks[0]
    lines = [l for l in first_proc.split("\n") if l and ":" in l]
    
    cpu_info = {}
    for line in lines:
        parts = line.split(":", 1)
        key = parts[0].strip()
        if key.startswith("\t"):
            key = key[1:]
        
        value = parts[1].strip()
        if value.startswith("\t"):
            value = value[1:]
            
        cpu_info[key] = value
        
    return cpu_info

def check_dmi_product_name():
    for path in ["/sys/class/dmi/id/product_name", "/sys/devices/virtual/dmi/id/product_name"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip()
            except Exception:
                pass
    return ""

def get_amd_zen_gen(family, model, model_name):
    if family == 23:
        if model in (1, 17, 8):
            return 1
        elif model in (49, 96, 113):
            return 2
        if 0 <= model <= 47:
            return 1
        elif 48 <= model <= 175:
            return 2
        return 2
    elif family == 25:
        if (0 <= model <= 15) or (32 <= model <= 95):
            return 3
        elif (16 <= model <= 31) or (96 <= model <= 175):
            return 4
        if (0 <= model <= 47) or model == 80:
            return 3
        elif model in (97, 24, 17):
            return 4
        return 3
    elif family == 26:
        return 5
    
    model_name = model_name or ""
    match = re.search(r'\b([1-9])(\d)(\d)(\d)\b', model_name)
    if match:
        d1 = int(match.group(1))
        d3 = int(match.group(3))
        if d1 == 9:
            return 5
        elif d1 == 8:
            return d3 if d3 in (3, 4) else 4
        elif d1 == 7:
            return d3 if d3 in (2, 3, 4) else 4
        elif d1 == 6:
            return 3
        elif d1 == 5:
            return 3
        elif d1 == 4:
            return 2
        elif d1 == 3:
            if "g" in model_name.lower():
                return 1
            return 2
        elif d1 in (1, 2):
            return 1
            
    model_name_lower = model_name.lower()
    if "zen 5" in model_name_lower or "ryzen 9000" in model_name_lower:
        return 5
    if "zen 4" in model_name_lower or "ryzen 7000" in model_name_lower or "ryzen 8000" in model_name_lower:
        return 4
    if "zen 3" in model_name_lower or "ryzen 5000" in model_name_lower or "ryzen 6000" in model_name_lower:
        return 3
    if "zen 2" in model_name_lower or "ryzen 3000" in model_name_lower or "ryzen 4000" in model_name_lower:
        return 2
    if "zen+" in model_name_lower or "ryzen 2000" in model_name_lower:
        return 1
    if "zen 1" in model_name_lower or "ryzen 1000" in model_name_lower:
        return 1

    return 0

def get_intel_gen(model_name):
    name = model_name or ""
    
    match_core = re.search(r'i[3579]-(\d{1,2})\d{3}', name)
    if match_core:
        return int(match_core.group(1))
    
    match_ultra = re.search(r'Ultra\s+[3579]\s+([12])\d\d', name)
    if match_ultra:
        series = int(match_ultra.group(1))
        return 13 + series
        
    if "Ultra" in name:
        return 14

    if any(x in name for x in ["N95", "N97"]):
        return 9
    if any(x in name for x in ["N100", "N200", "N300"]):
        return 12
        
    if any(x in name for x in ["i3-15", "i5-15", "i7-15", "i9-15"]):
        return 15
    if any(x in name for x in ["i3-14", "i5-14", "i7-14", "i9-14"]):
        return 14
    if any(x in name for x in ["i3-13", "i5-13", "i7-13", "i9-13"]):
        return 13
    if any(x in name for x in ["i3-12", "i5-12", "i7-12", "i9-12"]):
        return 12
    if any(x in name for x in ["i3-11", "i5-11", "i7-11", "i9-11"]):
        return 11
    if any(x in name for x in ["i3-10", "i5-10", "i7-10", "i9-10"]):
        return 10
    if any(x in name for x in ["i3-9", "i5-9", "i7-9", "i9-9"]):
        return 9
        
    return 0

def detect():
    cpu_info = parse_cpuinfo()
    
    cpu_vendor = "unknown"
    if cpu_info is not None:
        raw_vendor = cpu_info.get("vendor_id", "")
        if "AMD" in raw_vendor:
            cpu_vendor = "amd"
        elif "Intel" in raw_vendor:
            cpu_vendor = "intel"
            
    cpu_family = 0
    if cpu_info is not None:
        try:
            cpu_family = int(cpu_info.get("cpu family", "0"))
        except ValueError:
            pass
            
    cpu_model = 0
    if cpu_info is not None:
        try:
            cpu_model = int(cpu_info.get("model", "0"))
        except ValueError:
            pass
            
    model_name = ""
    if cpu_info is not None:
        model_name = cpu_info.get("model name", "")
        
    amd_zen_gen = get_amd_zen_gen(cpu_family, cpu_model, model_name) if cpu_vendor == "amd" else 0
            
    intel_gen = get_intel_gen(model_name) if cpu_vendor == "intel" else 0
            
    dmi_product = check_dmi_product_name()
    is_steam_deck = (
        (cpu_vendor == "amd" and cpu_family == 23 and cpu_model == 96)
        or any(x in model_name for x in ["0405", "Aerith", "Sephiroth", "Galileo"])
        or any(x in dmi_product for x in ["Steam Deck", "Aerith", "Sephiroth", "Galileo"])
    )
    
    should_disable_umip = (
        (cpu_vendor == "intel" and intel_gen >= 9)
        or (cpu_vendor == "amd" and amd_zen_gen >= 2)
        or is_steam_deck
    )
    
    should_enable_cpuid_fault_emulation = (
        (cpu_vendor == "amd" and 1 <= amd_zen_gen <= 3)
        or is_steam_deck
    )
    
    result = {
        "cpuVendor": cpu_vendor,
        "cpuFamily": cpu_family,
        "cpuModel": cpu_model,
        "modelName": model_name,
        "amdZenGen": amd_zen_gen,
        "intelGen": intel_gen,
        "isSteamDeck": is_steam_deck,
        "disableUmip": should_disable_umip,
        "cpuidFaultEmulation": should_enable_cpuid_fault_emulation
    }
    
    if dmi_product:
        result["dmiProduct"] = dmi_product
        
    return result

def main():
    data = detect()
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
