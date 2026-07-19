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
        description = "Auto-load the module at boot via boot.kernelModules.";
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

    boot.kernelModules =
      lib.mkIf
      (cfg.cpuidFaultEmulation.enable && cfg.cpuidFaultEmulation.autoLoad)
      ["cpuid_fault_emulation"];
  };
}
