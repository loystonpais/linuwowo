# linuwowo

Provides NixOS modules for cpuid_fault_emulation, LinUwUx patched proton and other goodies.

## Usage

### 1. Generate System Config JSON

Run the detector to analyze your CPU and write the config JSON to a file:

```bash
nix run github:loystonpais/linuwowo#detect > linuwowo.json
```

### 2. Add to Flake Inputs

In your `flake.nix`:

```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    linuwowo = {
      url = "github:loystonpais/linuwowo";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, linuwowo, ... }@inputs: {
    nixosConfigurations.my-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        linuwowo.nixosModules.default
        ./configuration.nix
      ];
    };
  };
}
```

### 3. Configure in NixOS

In your `configuration.nix` (make sure `linuwowo.json` is in the same directory):

```nix
{
  programs.linuwowo = {
    enable = true;
    json = ./linuwowo.json;
    
    # Optional: Automatically start the cpuid-fault-emulation service at boot.
    # If false, you can start/stop the service manually.
    # cpuidFaultEmulation.autoLoad = true; 
  };
}
```

## CPUID Fault Emulation Service

A systemd service named `cpuid-fault-emulation` is created when CPUID fault emulation is enabled. It manages loading and unloading of the module.

If `cpuidFaultEmulation.autoLoad` is `false` (default), you can still start/stop the service manually:

```bash
# Unload KVM and load CPUID fault emulation
sudo systemctl start cpuid-fault-emulation

# Unload CPUID fault emulation and restore KVM
sudo systemctl stop cpuid-fault-emulation
```

---

# Credits

- <https://github.com/Zerodya/nix-config/blob/cb4934ba79da193ccece91d551035cfabf74a69d/pkgs/cpuid-fault-emulation/default.nix>
- <https://github.com/pacjo/d*****-***>
