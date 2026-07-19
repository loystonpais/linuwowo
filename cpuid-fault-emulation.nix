{
  stdenv,
  kernel,
}:
stdenv.mkDerivation {
  pname = "cpuid_fault_emulation";
  version = builtins.elemAt (builtins.match ".*PACKAGE_VERSION=\"([^\"]+)\".*" (builtins.replaceStrings ["\n"] [" "] (builtins.readFile ./cpuid_fault_emulation/dkms.conf))) 0;

  src = ./cpuid_fault_emulation;

  nativeBuildInputs = kernel.moduleBuildDependencies;
  hardeningDisable = [
    "pic"
    "format"
  ];

  makeFlags = [
    "KERNEL=${kernel.modDirVersion}"
  ];

  # Patch the hardcoded host paths to point into the Nix store
  postPatch = ''
    substituteInPlace Makefile \
      --replace "/lib/modules/" "${kernel.dev}/lib/modules/"
  '';

  installPhase = ''
    install -D cpuid_fault_emulation.ko \
      $out/lib/modules/${kernel.modDirVersion}/extra/cpuid_fault_emulation.ko
  '';

  meta.platforms = ["x86_64-linux"];
}
