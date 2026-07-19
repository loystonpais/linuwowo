{
  description = "Denuvowo Nix";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/b5aa0fbd538984f6e3d201be0005b4463d8b09f8";

  outputs = {self, ...} @ inputs: let
    inherit (inputs.nixpkgs) lib;

    supportedSystems = [
      "x86_64-linux"
      "aarch64-linux"
    ];

    forEachSupportedSystem = f:
      lib.genAttrs supportedSystems (
        system:
          f {
            inherit system;
            pkgs = import inputs.nixpkgs {
              inherit system;
              config.allowUnfree = true;
            };
          }
      );
  in {
    packages = forEachSupportedSystem (
      {
        pkgs,
        system,
      }: {
        detect = pkgs.writers.writePython3Bin "detect" {doCheck = false;} (builtins.readFile ./detect.py);
        cpuid-fault-emulation = pkgs.callPackage ./cpuid-fault-emulation.nix {
          kernel = pkgs.linux;
        };
      }
    );

    devShells = forEachSupportedSystem (
      {
        pkgs,
        system,
      }: {
        default = pkgs.mkShellNoCC {
          packages = with pkgs; [
            self.formatter.${system}
            self.packages.${system}.detect
          ];
        };
      }
    );

    formatter = forEachSupportedSystem ({pkgs, ...}: pkgs.alejandra);

    nixosModules.default = import ./linuwowo.nix;
  };
}
