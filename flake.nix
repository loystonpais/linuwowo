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
      }: let
        releases = builtins.fromJSON (builtins.readFile ./gh-releases.json);
        allAssets = builtins.concatMap (release: release.assets) releases;
        protonAssets =
          builtins.filter (
            asset:
              (lib.hasPrefix "GE-Proton" asset.name) && (lib.hasSuffix ".tar.gz" asset.name)
          )
          allAssets;
        extractSha256 = digest: let
          hasPrefix = lib.hasPrefix "sha256:" digest;
        in
          if hasPrefix
          then lib.removePrefix "sha256:" digest
          else digest;
        protonPackages = builtins.listToAttrs (map (asset: let
            pkgName = lib.removeSuffix ".tar.gz" asset.name;
            tarball = pkgs.fetchurl {
              name = asset.name;
              url = asset.browser_download_url;
              sha256 = extractSha256 asset.digest;
            };
          in {
            name = pkgName;
            value = pkgs.runCommand pkgName {} ''
              mkdir -p $out
              tar -xf ${tarball} --strip-components=1 -C $out
            '';
          })
          protonAssets);
      in
        {
          detect = pkgs.writers.writePython3Bin "detect" {doCheck = false;} (builtins.readFile ./detect.py);
          cpuid-fault-emulation = pkgs.callPackage ./cpuid-fault-emulation.nix {
            kernel = pkgs.linux;
          };
        }
        // protonPackages
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
