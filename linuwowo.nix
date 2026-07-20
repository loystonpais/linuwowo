{
  config,
  lib,
  pkgs,
  ...
}: let
  cfg = config.programs.linuwowo;

  jsonData =
    if cfg.json != null
    then builtins.fromJSON (builtins.readFile cfg.json)
    else throw "Attempted to access default values from JSON, but programs.linuwowo.json is not set.";
in {
  options.programs.linuwowo = {
    enable = lib.mkEnableOption "linuwowo";

    json = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Path to the json file.";
    };

    disableUmip = lib.mkOption {
      type = lib.types.bool;
      default = jsonData.disableUmip;
      description = "Disables UMIP CPU feature.";
    };

    cpuidFaultEmulation = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = jsonData.cpuidFaultEmulation;
        description = "Build and load the AMD CPUID fault emulation kernel module.";
      };

      package = lib.mkOption {
        type = lib.types.package;
        default = config.boot.kernelPackages.callPackage ./cpuid-fault-emulation.nix {};
        defaultText = lib.literalExpression "config.boot.kernelPackages.callPackage ./cpuid-fault-emulation.nix {}";
        description = "The CPUID fault emulation kernel module package to use.";
      };

      autoLoad = lib.mkOption {
        type = lib.types.bool;
        default = false;
        description = "Auto-load the module at boot via the cpuid-fault-emulation systemd service.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.json != null;
        message = "programs.linuwowo.json must be set when programs.linuwowo.enable is true.";
      }
    ];

    boot.kernelParams = lib.mkIf cfg.disableUmip ["clearcpuid=umip"];

    boot.extraModulePackages = lib.mkIf cfg.cpuidFaultEmulation.enable [
      cfg.cpuidFaultEmulation.package
    ];

    systemd.services.cpuid-fault-emulation = lib.mkIf cfg.cpuidFaultEmulation.enable {
      description = "CPUID Fault Emulation Service";
      wantedBy = lib.mkIf cfg.cpuidFaultEmulation.autoLoad ["multi-user.target"];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = pkgs.writeShellScript "cpuid-fault-emulation-start" ''
          export PATH=${lib.makeBinPath (with pkgs; [kmod gnugrep])}:$PATH
          if lsmod | grep -q "^kvm_amd"; then
            modprobe -r kvm_amd
          elif lsmod | grep -q "^kvm_intel"; then
            modprobe -r kvm_intel
          fi
          modprobe -r kvm || true
          modprobe cpuid_fault_emulation
        '';
        ExecStop = pkgs.writeShellScript "cpuid-fault-emulation-stop" ''
          export PATH=${lib.makeBinPath (with pkgs; [kmod gnugrep])}:$PATH
          modprobe -r cpuid_fault_emulation
          modprobe kvm || true
          if grep -q "AuthenticAMD" /proc/cpuinfo; then
            modprobe kvm_amd || true
          elif grep -q "GenuineIntel" /proc/cpuinfo; then
            modprobe kvm_intel || true
          fi
        '';
      };
    };
  };
}
