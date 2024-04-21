{
  description = "ds1000z-tools";

  inputs.nixpkgs.url = "nixpkgs/nixos-23.11";
  inputs.utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, utils }:
    utils.lib.eachSystem utils.lib.defaultSystems (system:
      let
        pkgs = nixpkgs.legacyPackages."${system}";
        python = pkgs.python3;
      in
      rec {
        packages.ds1000z-tools = python.pkgs.buildPythonPackage rec {
          name = "ds1000z-tools";
          src = ./.;
          propagatedBuildInputs = with python.pkgs; [ numpy pyvisa pyvisa-py tqdm ];
          nativeBuildInputs = with python.pkgs; [ setuptools ];
          pyproject = true;

          doCheck = true;
          nativeCheckInputs = with python.pkgs; [ pytest pytestCheckHook ];
          pytestFlagsArray = [ "ds1000z_tools" "-x" ];

          meta.mainProgram = "ds1000z-tools";
        };

        defaultPackage = packages.ds1000z-tools;

        devShells.ds1000z-tools = packages.ds1000z-tools.overridePythonAttrs (attrs: {
          nativeBuildInputs = attrs.nativeBuildInputs ++ [
            python.pkgs.mypy
            python.pkgs.black
            pkgs.nixpkgs-fmt
          ];
        });

        devShell = devShells.ds1000z-tools;
      }
    );
}


