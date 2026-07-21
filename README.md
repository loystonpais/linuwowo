# linuwowo

Provides LinUwUx patched proton, NixOS modules for cpuid_fault_emulation and other goodies.

## Usage (NixOS Module)

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

#### CPUID Fault Emulation Service

A systemd service named `cpuid-fault-emulation` is created when CPUID fault emulation is enabled. It manages loading and unloading of the module.

If `cpuidFaultEmulation.autoLoad` is `false` (default), you can still start/stop the service manually:

```bash
# Unload KVM and load CPUID fault emulation
sudo systemctl start cpuid-fault-emulation

# Unload CPUID fault emulation and restore KVM
sudo systemctl stop cpuid-fault-emulation
```

## Usage (Proton)

### Method 1: Manual Installation (GitHub Releases)

You can download the LinUwUx-patched Proton versions directly from the [GitHub Releases](https://github.com/loystonpais/linuwowo/releases).

To use them, extract the tarball and symlink the directory to the path where your game launcher looks for compatibility tools.

For example, for **Heroic Games Launcher**:

```bash
# Extract the downloaded archive
tar -xf ~/Downloads/GE-Proton11-1-LinUwUx-patch.tar.gz -C ~/Downloads/

# Create the target directory if it doesn't exist
mkdir -p ~/.config/heroic/tools/proton/

# Symlink it into Heroic's proton directory
ln -s ~/Downloads/GE-Proton11-1-LinUwUx-patch ~/.config/heroic/tools/proton/GE-Proton11-1-LinUwUx-patch
```

For **Steam**:

```bash
# Create the target directory if it doesn't exist
mkdir -p ~/.steam/root/compatibilitytools.d/

# Symlink it into Steam's compatibility tools directory
ln -s ~/Downloads/GE-Proton11-1-LinUwUx-patch ~/.steam/root/compatibilitytools.d/GE-Proton11-1-LinUwUx-patch
```

### Method 2: Nix Flake Packages

This flake also packages the GitHub Proton releases directly, making them available under `packages.${system}`.

You can see all available Proton packages in this flake by running:

```bash
nix flake show github:loystonpais/linuwowo
```

#### Symlinking via Home Manager

If you are using **Home Manager**, you can declare the symlink in your configuration directly without having to download or manage files manually.

Add the `linuwowo` input to your configuration, and then define the symlink:

```nix
{ inputs, pkgs, ... }:
let
  system = pkgs.stdenv.hostPlatform.system;
in {
  # For Heroic Games Launcher
  home.file.".config/heroic/tools/proton/GE-Proton11-1-LinUwUx-patch".source =
    inputs.linuwowo.packages.${system}.GE-Proton11-1-LinUwUx-patch;

  # For Steam
  home.file.".steam/root/compatibilitytools.d/GE-Proton11-1-LinUwUx-patch".source =
    inputs.linuwowo.packages.${system}.GE-Proton11-1-LinUwUx-patch;
}
```

---

# Credits

- <https://github.com/Zerodya/nix-config/blob/cb4934ba79da193ccece91d551035cfabf74a69d/pkgs/cpuid-fault-emulation/default.nix>
- <https://github.com/pacjo/d*****-***>
