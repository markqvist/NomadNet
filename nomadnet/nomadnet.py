#!/usr/bin/env python3

from ._version import __version__

import io
import argparse
import nomadnet


def program_setup(configdir, rnsconfigdir, daemon, console):
    app = nomadnet.NomadNetworkApp(
        configdir = configdir,
        rnsconfigdir = rnsconfigdir,
        daemon = daemon,
        force_console = console,
    )

def main():
    try:
        parser = argparse.ArgumentParser(description="Nomad Network Client")
        parser.add_argument("--config", action="store", default=None, help="path to alternative Nomad Network config directory", type=str)
        parser.add_argument("--rnsconfig", action="store", default=None, help="path to alternative Reticulum config directory", type=str)
        parser.add_argument("-t", "--textui", action="store_true", default=False, help="run Nomad Network in text-UI mode")
        parser.add_argument("-d", "--daemon", action="store_true", default=False, help="run Nomad Network in daemon mode")
        parser.add_argument("-c", "--console", action="store_true", default=False, help="in daemon mode, log to console instead of file")
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

        console = False
        if args.daemon:
            daemon = True
            if args.console:
                console = True
        else:
            daemon = False

        if args.textui:
            daemon = False

        program_setup(configarg, rnsconfigarg, daemon, console)

    except KeyboardInterrupt:
        print("")
        exit()

if __name__ == "__main__":
    main()