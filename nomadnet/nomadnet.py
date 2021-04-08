#!/usr/bin/env python3

from ._version import __version__

import argparse
import nomadnet


def program_setup(configdir, rnsconfigdir):
    app = nomadnet.NomadNetworkApp(configdir = configdir, rnsconfigdir = rnsconfigdir)

def main():
    try:
        parser = argparse.ArgumentParser(description="Nomad Network Client")
        parser.add_argument("--config", action="store", default=None, help="path to alternative Nomad Network config directory", type=str)
        parser.add_argument("--rnsconfig", action="store", default=None, help="path to alternative Reticulum config directory", type=str)
        parser.add_argument("--version", action="version", version="Nomad Network Client {version}".format(version=__version__))
        
        args = parser.parse_args()

        if args.config:
            configarg = args.config
        else:
            configarg = None

        if args.rnsconfig:
            rnsconfigarg = args.rnsconfig
        else:
            rnsconfigarg = None

        program_setup(configarg, rnsconfigarg)

    except KeyboardInterrupt:
        print("")
        exit()

if __name__ == "__main__":
    main()