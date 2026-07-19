#!/usr/bin/env python3
# Patch tool to apply the LinUwUx patch to GE-Proton / Proton repository.

import os
import re
import sys
import argparse
import subprocess


def patch_proton(proton_path, verbose=False):
    if verbose:
        print(f"[+] Reading {proton_path}...")
    with open(proton_path, "r") as f:
        content = f.read()

    modified = False
    if "PROTON_DISABLE_LSTEAMCLIENT" not in content:
        # Find self.dlloverrides block
        match = re.search(r"self\.dlloverrides\s*=\s*\{[^}]*\}", content)
        if match:
            dlloverrides_block = match.group(0)
            new_block = dlloverrides_block
            if "reflex.dll" not in dlloverrides_block:
                new_block = dlloverrides_block.replace(
                    "{",
                    '{\n                "winmm": "n,b",\n                "version.dll": "n,b",\n                "reflex.dll": "n,b",',
                    1,
                )

            insertion = '\n\n        if "PROTON_DISABLE_LSTEAMCLIENT" not in os.environ:\n            os.environ["PROTON_DISABLE_LSTEAMCLIENT"] = "1"\n            self.env["PROTON_DISABLE_LSTEAMCLIENT"] = "1"'

            content = content.replace(dlloverrides_block, new_block + insertion, 1)
            modified = True

    if modified:
        with open(proton_path, "w") as f:
            f.write(content)
        print("[+] Successfully patched proton script.")
    else:
        print("[*] Proton script already patched or skipped.")


def patch_signal_x86_64(signal_path, verbose=False):
    if verbose:
        print(f"[+] Reading {signal_path}...")
    with open(signal_path, "r") as f:
        content = f.read()

    modified = False

    # 1. Globals
    if "TargetSysHandler" not in content:
        globals_code = """
// This will point to the games memory region where syscall spoofing is happening
uint64_t TargetSysHandler = 0;
uint64_t SyscallBypassMagic = 0x1337133713371337;
// Spoofed CPUID values - will be set based on CPU vendor
static unsigned int spoof_leaf40000000_eax, spoof_leaf40000000_ebx, spoof_leaf40000000_ecx, spoof_leaf40000000_edx;
static unsigned int spoof_leaf40000001_eax, spoof_leaf40000001_ebx, spoof_leaf40000001_ecx, spoof_leaf40000001_edx;
static unsigned int spoof_leaf1_eax, spoof_leaf1_ebx, spoof_leaf1_ecx, spoof_leaf1_edx;

#ifndef ARCH_SET_CPUID
#define ARCH_SET_CPUID 0x1012
#endif
"""
        pos = content.find("struct xcontext")
        if pos != -1:
            content = content[:pos] + globals_code + "\n" + content[pos:]
            modified = True

    # 2. Syscall Bypass inside sigsys_handler
    if "SyscallBypassMagic" not in content:
        syscall_bypass_code = """
    ucontext_t *ctx = sigcontext;
    
    __uint128_t *xmm_regs = (__uint128_t *)ctx->uc_mcontext.fpregs->_xmm;
    if (TargetSysHandler != 0 && (xmm_regs[5] & 0xFFFFFFFFFFFFFFFF) != 0x1337133713371337) {
        xmm_regs[4] = ctx->uc_mcontext.gregs[REG_RAX] & 0xFFFFFFFF;
        ctx->uc_mcontext.gregs[REG_RAX] = ctx->uc_mcontext.gregs[REG_RCX];
        ctx->uc_mcontext.gregs[REG_RCX] = TargetSysHandler;
        ctx->uc_mcontext.gregs[REG_RIP] = TargetSysHandler;
        return;
    }
    if ((xmm_regs[5] & 0xFFFFFFFFFFFFFFFF) == 0x1337133713371337) {
        xmm_regs[5] = 0;
        //MESSAGE("SyscallBypassMagic!\\n");
    }
"""
        sigsys_pos = content.find("sigsys_handler")
        if sigsys_pos != -1:
            frame_pos = content.find("get_syscall_frame()", sigsys_pos)
            if frame_pos != -1:
                semicolon_pos = content.find(";", frame_pos)
                if semicolon_pos != -1:
                    end_of_line = content.find("\n", semicolon_pos)
                    content = (
                        content[: end_of_line + 1]
                        + syscall_bypass_code
                        + content[end_of_line + 1 :]
                    )
                    modified = True

    # 3. patch_kuser_shared_data function
    if "patch_kuser_shared_data" not in content:
        patch_kuser_shared_data_code = """
/**
* Patch KUSER_SHARED_DATA with spoofed values
*/
static void patch_kuser_shared_data(void) {
    UINT8 *kuser = (UINT8 *)0x000000007FFE0000UL;
    
    // Make memory writable
    size_t page_size = sysconf(_SC_PAGESIZE);
    void *page_start = (void *)((uintptr_t)0x000000007FFE0000UL & ~(page_size - 1));
    
    if (mprotect(page_start, page_size, PROT_READ | PROT_WRITE) == -1) {
        MESSAGE("Failed to make kuser_shared_data writable: %s\\n", strerror(errno));
        return;
    }
    
    memcpy((void*)(kuser + 0x30), "\\x43\\x00\\x3A\\x00\\x5C\\x00\\x57\\x00\\x69\\x00\\x6E\\x00\\x64\\x00\\x6F\\x00\\x77\\x00\\x73\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00", 0x104);
    
    *(UINT64*)(kuser + 0x260) = 0x0100006658;
    *(UINT32*)(kuser + 0x268) = 0x090001;
    *(UINT32*)(kuser + 0x26C) = 0x0A;
    *(UINT32*)(kuser + 0x270) = 0x00;

    // ProcessorFeatures
    *(UINT32*)(kuser + 0x274) = 0x01010000;
    *(UINT32*)(kuser + 0x278) = 0x010000;
    *(UINT32*)(kuser + 0x27C) = 0x010101;
    *(UINT32*)(kuser + 0x280) = 0x010101;
    *(UINT32*)(kuser + 0x284) = 0x0100;
    *(UINT32*)(kuser + 0x288) = 0x01010101;
    *(UINT32*)(kuser + 0x28C) = 0x0;
    *(UINT32*)(kuser + 0x290) = 0x01;
    *(UINT32*)(kuser + 0x294) = 0x01000101;
    *(UINT32*)(kuser + 0x298) = 0x01010101;
    *(UINT32*)(kuser + 0x29C) = 0x010001;
    *(UINT32*)(kuser + 0x2A0) = 0x0;
    *(UINT32*)(kuser + 0x2A4) = 0x0;
    *(UINT32*)(kuser + 0x2A8) = 0x0;
    *(UINT32*)(kuser + 0x2AC) = 0x0;
    *(UINT32*)(kuser + 0x2B0) = 0x1;

    // Disable specific features (byte-level patches)
    *(UINT8*)(kuser + 0x290) = 0x0;    // Disable MONITORX support
    *(UINT8*)(kuser + 0x294) = 0x0;    // Disable RDTSCP support
    *(UINT8*)(kuser + 0x295) = 0x0;    // Disable RDPID support
    *(UINT8*)(kuser + 0x297) = 0x0;    // Disable RDRAND support

    if (getenv("PROTON_AVX") == NULL || (getenv("PROTON_AVX") != NULL && strcmp(getenv("PROTON_AVX"), "1")) != 0){
        // XSAVE related stuff
        *(UINT8*)(kuser + 0x285) = 0x0;    // Disable XSAVE support
        *(UINT8*)(kuser + 0x29B) = 0x0;    // Disable AVX support
        *(UINT8*)(kuser + 0x29C) = 0x0;    // Disable AVX2 support
    }

    *(UINT64*)(kuser + 0x3D8) = 0x0;   // EnabledFeatures
    *(UINT64*)(kuser + 0x3E0) = 0x0;   // EnabledVolatileFeatures
    *(UINT32*)(kuser + 0x3EC) = 0x0;   // ControlFlags
    memset((void*)(kuser + 0x3F0), 0x00, 0x200);   // Features
    *(UINT64*)(kuser + 0x5F0) = 0x0;   // EnabledSupervisorFeatures
    *(UINT64*)(kuser + 0x5F8) = 0x0;   // AlignedFeatures
    memset((void*)(kuser + 0x604), 0x00, 0x200);   // AllFeatures
    *(UINT64*)(kuser + 0x808) = 0x0;   // EnabledUserVisibleSupervisorFeatures
    *(UINT64*)(kuser + 0x810) = 0x0;   // ExtendedFeatureDisableFeatures

    *(UINT64*)(kuser + 0x2D0) = 0x320A0000000110;
    *(UINT64*)(kuser + 0x2E8) = 0x0100007FB10B;
    *(UINT32*)(kuser + 0x2F4) = 0x0;
    *(UINT64*)(kuser + 0x36C) = 0x0;
    *(UINT64*)(kuser + 0x374) = 0x0;
    *(UINT32*)(kuser + 0x37C) = 0x1;
    *(UINT64*)(kuser + 0x3C0) = 0x83000100000010;

    *(UINT32*)(kuser + 0xFFC) = 0x13371337;
}
"""
        segv_pos = content.find("static void segv_handler")
        if segv_pos != -1:
            content = (
                content[:segv_pos]
                + patch_kuser_shared_data_code
                + "\n\n"
                + content[segv_pos:]
            )
            modified = True

    # 4. CPUID spoofing inside segv_handler
    if "Spoofing CPUID leaf" not in content:
        cpuid_spoof_code = """
    unsigned int leaf;
    unsigned int subleaf;
    ucontext_t *uc;
    unsigned char *rip;

    uc = (ucontext_t *)sigcontext;
    rip = (unsigned char *)uc->uc_mcontext.gregs[REG_RIP];
    leaf = ucontext->uc_mcontext.gregs[REG_RAX];
    subleaf = ucontext->uc_mcontext.gregs[REG_RCX];
    if ((siginfo->si_code == SI_KERNEL || leaf == 0x336933) && rip[0] == 0x0F && rip[1] == 0xA2) {
        // Spoof CPUID results based on leaf
        switch (leaf) {
            case 1:
                uc->uc_mcontext.gregs[REG_RAX] = spoof_leaf1_eax;
                uc->uc_mcontext.gregs[REG_RBX] = spoof_leaf1_ebx;
                uc->uc_mcontext.gregs[REG_RCX] = spoof_leaf1_ecx | (TargetSysHandler ? 0 : (0x1 << 31));
                uc->uc_mcontext.gregs[REG_RDX] = spoof_leaf1_edx;
                break;

            case 0x40000000:
                uc->uc_mcontext.gregs[REG_RAX] = spoof_leaf40000000_eax;
                uc->uc_mcontext.gregs[REG_RBX] = spoof_leaf40000000_ebx;
                uc->uc_mcontext.gregs[REG_RCX] = spoof_leaf40000000_ecx;
                uc->uc_mcontext.gregs[REG_RDX] = spoof_leaf40000000_edx;
                break;

            case 0x40000001:
                uc->uc_mcontext.gregs[REG_RAX] = spoof_leaf40000001_eax;
                uc->uc_mcontext.gregs[REG_RBX] = spoof_leaf40000001_ebx;
                uc->uc_mcontext.gregs[REG_RCX] = spoof_leaf40000001_ecx;
                uc->uc_mcontext.gregs[REG_RDX] = spoof_leaf40000001_edx;
                break;

            case 0x80000002:
                uc->uc_mcontext.gregs[REG_RAX] = 0x756E6544;
                uc->uc_mcontext.gregs[REG_RBX] = 0x4F774F76;
                uc->uc_mcontext.gregs[REG_RCX] = 0x55504320;
                uc->uc_mcontext.gregs[REG_RDX] = 0x31204020;
                break;

            case 0x80000003:
                uc->uc_mcontext.gregs[REG_RAX] = 0x20373333;
                uc->uc_mcontext.gregs[REG_RBX] = 0x007A4847;
                uc->uc_mcontext.gregs[REG_RCX] = 0x00000000;
                uc->uc_mcontext.gregs[REG_RDX] = 0x00000000;
                break;

            case 0x80000004:
                uc->uc_mcontext.gregs[REG_RAX] = 0x0;
                uc->uc_mcontext.gregs[REG_RBX] = 0x0;
                uc->uc_mcontext.gregs[REG_RCX] = 0x0;
                uc->uc_mcontext.gregs[REG_RDX] = 0x0;
                break;

            case 0x336933:
                MESSAGE("Spoofing CPUID leaf %x\\n", leaf);
                TargetSysHandler = uc->uc_mcontext.gregs[REG_RCX];
                patch_kuser_shared_data();
                uc->uc_mcontext.gregs[REG_RAX] = 0x0;
                uc->uc_mcontext.gregs[REG_RBX] = 0x0;
                uc->uc_mcontext.gregs[REG_RCX] = 0x0;
                uc->uc_mcontext.gregs[REG_RDX] = 0x0;
                break;
                
            case 0x336967:
                MESSAGE("Setting Faketime to %llx... \\n", uc->uc_mcontext.gregs[REG_RCX]);
                SERVER_START_REQ( set_faketime )
                {
                    req->faketime = uc->uc_mcontext.gregs[REG_RCX];
                    wine_server_call( req );
                }
                SERVER_END_REQ;
                uc->uc_mcontext.gregs[REG_RAX] = 0x0;
                uc->uc_mcontext.gregs[REG_RBX] = 0x0;
                uc->uc_mcontext.gregs[REG_RCX] = 0x0;
                uc->uc_mcontext.gregs[REG_RDX] = 0x0;
                break;

            default:
                syscall(SYS_arch_prctl, ARCH_SET_CPUID, 1);
                __asm__ volatile(
                        "cpuid"
                        : "=a"(uc->uc_mcontext.gregs[REG_RAX]), 
                          "=b"(uc->uc_mcontext.gregs[REG_RBX]), 
                          "=c"(uc->uc_mcontext.gregs[REG_RCX]), 
                          "=d"(uc->uc_mcontext.gregs[REG_RDX])
                        : "a"(leaf), "c"(subleaf)
                        : "memory"
                    );
                syscall(SYS_arch_prctl, ARCH_SET_CPUID, 0);
        }

        uc->uc_mcontext.gregs[REG_RIP] += 2;
        return;
    }
"""
        segv_pos = content.find("static void segv_handler")
        if segv_pos != -1:
            target_pos = content.find(
                "rec.ExceptionAddress = (void *)RIP_sig(ucontext);", segv_pos
            )
            if target_pos != -1:
                content = (
                    content[:target_pos]
                    + cpuid_spoof_code
                    + "\n\n    "
                    + content[target_pos:]
                )
                modified = True

    # 5. detect_cpu_vendor function
    if "detect_cpu_vendor" not in content:
        detect_cpu_vendor_code = """
// Function to detect CPU vendor at startup
static void detect_cpu_vendor(void) {
    unsigned int eax, ebx, ecx, edx;
    int avx = 0;
    if (getenv("PROTON_AVX") != NULL && strcmp(getenv("PROTON_AVX"), "1") == 0) avx = 1;
    
    __asm__ volatile(
        "cpuid"
        : "=a"(eax), "=b"(ebx), "=c"(ecx), "=d"(edx)
        : "a"(0)
        : "memory"
    );
    
    if (ebx == 0x756E6547 && edx == 0x49656E69 && ecx == 0x6C65746E) {
        spoof_leaf1_eax = 0x000A0655;
        spoof_leaf1_ebx = 0x00200800;
        if (avx) {
        	spoof_leaf1_ecx = 0x7BFAFBFF;
        } else spoof_leaf1_ecx = 0x01FAEBFF;
        spoof_leaf1_edx = 0xBFEBFBFF;
        
        spoof_leaf40000000_eax = 0x40000001;
        spoof_leaf40000000_ebx = 0x65707948;
        spoof_leaf40000000_ecx = 0x67624472;
        spoof_leaf40000000_edx = 0;
        
        spoof_leaf40000001_eax = 0x30237648;
        spoof_leaf40000001_ebx = 0;
        spoof_leaf40000001_ecx = 0;
        spoof_leaf40000001_edx = 0;
        
    } else if (ebx == 0x68747541 && edx == 0x69746E65 && ecx == 0x444D4163) {
        spoof_leaf1_eax = 0x00A20F12;
        spoof_leaf1_ebx = 0x00100800;
        if (avx) {
        	spoof_leaf1_ecx = 0x7AD8320B;
        } else spoof_leaf1_ecx = 0x00F8220B;
        spoof_leaf1_edx = 0x178BFBFF;
        
        spoof_leaf40000000_eax = 0x40000001;
        spoof_leaf40000000_ebx = 0x706D6953;
        spoof_leaf40000000_ecx = 0x7653656C;
        spoof_leaf40000000_edx = 0x2020206D;
        
        spoof_leaf40000001_eax = 0x30237648;
        spoof_leaf40000001_ebx = 0;
        spoof_leaf40000001_ecx = 0;
        spoof_leaf40000001_edx = 0;
    }
}
"""
        init_pos = content.find("void signal_init_process")
        if init_pos != -1:
            content = (
                content[:init_pos]
                + detect_cpu_vendor_code
                + "\n\n"
                + content[init_pos:]
            )
            modified = True

    # 6. Call detect_cpu_vendor and ARCH_SET_CPUID in signal_init_process
    if "detect_cpu_vendor()" not in content:
        init_pos = content.find("void signal_init_process")
        if init_pos != -1:
            sigsegv_pos = content.find("sigaction( SIGSEGV", init_pos)
            if sigsegv_pos != -1:
                end_of_line = content.find("\n", sigsegv_pos)
                content = (
                    content[: end_of_line + 1]
                    + "    detect_cpu_vendor();\n    syscall(SYS_arch_prctl, ARCH_SET_CPUID, 0);\n"
                    + content[end_of_line + 1 :]
                )
                modified = True

    if modified:
        with open(signal_path, "w") as f:
            f.write(content)
        print("[+] Successfully patched signal_x86_64.c.")
    else:
        print("[*] signal_x86_64.c already patched or skipped.")


def patch_wine_inf(wine_inf_path, verbose=False):
    print(f"[+] Patching {wine_inf_path}...")
    with open(wine_inf_path, "r") as f:
        content = f.read()

    line_to_add = 'HKLM,System\\CurrentControlSet\\Control\\IDConfigDB\\Hardware Profiles\\0001,"HwProfileGuid",,"{12345678-1234-1234-1234-123456789012}"'
    if "HwProfileGuid" not in content:
        content = content.rstrip() + "\n" + line_to_add + "\n"
        with open(wine_inf_path, "w") as f:
            f.write(content)
        print("[+] Successfully patched wine.inf.in.")
    else:
        print("[*] wine.inf.in already patched or skipped.")


def patch_fd(fd_path, verbose=False):
    print(f"[+] Patching {fd_path}...")
    with open(fd_path, "r") as f:
        content = f.read()

    modified = False

    # 1. Globals
    if "static timeout_t faketime = 0;" not in content:
        pos = content.find("timeout_t current_time;")
        if pos != -1:
            end_of_line = content.find("\n", pos)
            content = (
                content[: end_of_line + 1]
                + "\nstatic timeout_t faketime = 0;\n"
                + content[end_of_line + 1 :]
            )
            modified = True

    # 2. set_current_time subtraction
    time_pos = content.find("void set_current_time")
    if time_pos != -1:
        ticks_pos = content.find("ticks_1601_to_1970", time_pos)
        if ticks_pos != -1:
            ticks_pos2 = content.find(
                "ticks_1601_to_1970", ticks_pos + len("ticks_1601_to_1970")
            )
            if ticks_pos2 != -1:
                semicolon_pos = content.find(";", ticks_pos2)
                if semicolon_pos != -1:
                    statement = content[ticks_pos2:semicolon_pos]
                    if "- faketime" not in statement:
                        content = (
                            content[:semicolon_pos]
                            + " - faketime"
                            + content[semicolon_pos:]
                        )
                        modified = True

    # 3. DECL_HANDLER(set_faketime)
    if "DECL_HANDLER(set_faketime)" not in content:
        content = (
            content.rstrip()
            + "\n\nDECL_HANDLER(set_faketime)\n{\n    faketime = ((current_time >> 32) - req->faketime) << 32;\n}\n"
        )
        modified = True

    if modified:
        with open(fd_path, "w") as f:
            f.write(content)
        print("[+] Successfully patched fd.c.")
    else:
        print("[*] fd.c already patched or skipped.")


def patch_protocol_def(protocol_def_path, verbose=False):
    print(f"[+] Patching {protocol_def_path}...")
    with open(protocol_def_path, "r") as f:
        content = f.read()

    if "@REQ(set_faketime)" not in content:
        content = (
            content.rstrip()
            + "\n\n@REQ(set_faketime)\n    unsigned __int64 faketime;\n@REPLY\n@END\n"
        )
        with open(protocol_def_path, "w") as f:
            f.write(content)
        print("[+] Successfully patched protocol.def.")
    else:
        print("[*] protocol.def already patched or skipped.")


def run_make_requests(wine_root, verbose=False):
    make_requests_path = os.path.join(wine_root, "tools", "make_requests")
    if os.path.exists(make_requests_path):
        print("[+] Regenerating wine server protocol headers via make_requests...")
        try:
            # First attempt to run it directly
            subprocess.run(
                [make_requests_path],
                cwd=wine_root,
                check=True,
                stdout=subprocess.PIPE if not verbose else None,
            )
            print("[+] Successfully regenerated wine server headers.")
        except (PermissionError, subprocess.CalledProcessError, OSError):
            # Fallback to run with perl explicitly
            try:
                subprocess.run(
                    ["perl", "./tools/make_requests"],
                    cwd=wine_root,
                    check=True,
                    stdout=subprocess.PIPE if not verbose else None,
                )
                print("[+] Successfully regenerated wine server headers.")
            except Exception as e:
                print(f"[-] Error running make_requests: {e}")
                print("    Please run: cd wine && perl ./tools/make_requests manually.")
    else:
        print("[-] Warning: make_requests tool not found. Skipping auto-regeneration.")


def get_paths(root_dir):
    root_dir = os.path.abspath(root_dir)

    # Auto-detect target repository root
    proton_path = os.path.join(root_dir, "proton")
    if not os.path.exists(proton_path):
        proton_path = os.path.join(root_dir, "..", "proton")
        if os.path.exists(proton_path):
            root_dir = os.path.abspath(os.path.join(root_dir, ".."))
        else:
            return None

    wine_root = os.path.join(root_dir, "wine")
    return {
        "root_dir": root_dir,
        "proton": proton_path,
        "wine_root": wine_root,
        "signal_x86_64": os.path.join(
            wine_root, "dlls", "ntdll", "unix", "signal_x86_64.c"
        ),
        "wine_inf": os.path.join(wine_root, "loader", "wine.inf.in"),
        "fd": os.path.join(wine_root, "server", "fd.c"),
        "protocol_def": os.path.join(wine_root, "server", "protocol.def"),
    }


def check_patches(paths, verbose=False):
    print(f"[*] Checking status of files in {paths['root_dir']}...")

    checks = [
        ("Proton script", paths["proton"], "PROTON_DISABLE_LSTEAMCLIENT"),
        ("signal_x86_64.c", paths["signal_x86_64"], "TargetSysHandler"),
        ("wine.inf.in", paths["wine_inf"], "HwProfileGuid"),
        ("fd.c", paths["fd"], "DECL_HANDLER(set_faketime)"),
        ("protocol.def", paths["protocol_def"], "@REQ(set_faketime)"),
    ]

    all_patched = True
    any_patched = False

    for label, path, pattern in checks:
        if not os.path.exists(path):
            print(
                f"  {label:<16}: \033[31mMISSING\033[0m ({os.path.relpath(path, paths['root_dir'])})"
            )
            all_patched = False
            continue

        with open(path, "r") as f:
            content = f.read()

        if pattern in content:
            print(f"  {label:<16}: \033[32mPATCHED\033[0m")
            any_patched = True
        else:
            print(f"  {label:<16}: \033[33mUNPATCHED\033[0m")
            all_patched = False

    return all_patched, any_patched


def revert_patches(paths, verbose=False):
    print(f"[*] Reverting patches in {paths['root_dir']}...")

    files_to_revert = [
        paths["proton"],
        paths["signal_x86_64"],
        paths["wine_inf"],
        paths["fd"],
        paths["protocol_def"],
    ]

    # Check if target is a git repository
    is_git = False
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=paths["root_dir"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        is_git = res.returncode == 0
    except Exception:
        pass

    if is_git:
        print("[+] Detected git repository. Reverting files via git checkout...")
        for path in files_to_revert:
            if os.path.exists(path):
                rel_path = os.path.relpath(path, paths["root_dir"])
                if verbose:
                    print(f"    git checkout -- {rel_path}")
                subprocess.run(
                    ["git", "checkout", "--", rel_path],
                    cwd=paths["root_dir"],
                    check=True,
                )
                print(f"[+] Reverted {os.path.basename(path)}")
        run_make_requests(paths["wine_root"], verbose)
        print("[+] Reversion finished successfully.")
    else:
        print(
            "[-] Error: Revert option requires the target repository to be a git repository."
        )
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Patch tool to apply the LinUwUx patch to GE-Proton / Proton repository."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the GE-Proton / Proton repository root (default: current directory)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check the patch status of target files",
    )
    group.add_argument(
        "--revert",
        "-r",
        action="store_true",
        help="Revert the applied patches (requires git worktree)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Output detailed actions"
    )

    args = parser.parse_args()

    paths = get_paths(args.path)
    if not paths:
        print(
            "[-] Error: Could not locate Proton root directory structure containing 'proton' and 'wine/'."
        )
        print("    Please specify the repository root or run inside the repository.")
        sys.exit(1)

    if args.check:
        check_patches(paths, args.verbose)
    elif args.revert:
        revert_patches(paths, args.verbose)
    else:
        # Default: Apply patches
        print(f"[*] Starting LinUwUx patch application at: {paths['root_dir']}")

        patch_proton(paths["proton"], args.verbose)

        if os.path.exists(paths["signal_x86_64"]):
            patch_signal_x86_64(paths["signal_x86_64"], args.verbose)
        else:
            print(f"[-] Warning: signal_x86_64.c not found at {paths['signal_x86_64']}")

        if os.path.exists(paths["wine_inf"]):
            patch_wine_inf(paths["wine_inf"], args.verbose)
        else:
            print(f"[-] Warning: wine.inf.in not found at {paths['wine_inf']}")

        if os.path.exists(paths["fd"]):
            patch_fd(paths["fd"], args.verbose)
        else:
            print(f"[-] Warning: fd.c not found at {paths['fd']}")

        if os.path.exists(paths["protocol_def"]):
            patch_protocol_def(paths["protocol_def"], args.verbose)
            run_make_requests(paths["wine_root"], args.verbose)
        else:
            print(f"[-] Warning: protocol.def not found at {paths['protocol_def']}")

        print("[+] Finished patch application.")


if __name__ == "__main__":
    main()
