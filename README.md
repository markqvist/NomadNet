# Nomad Network - Communicate Freely

*This repository is [a public mirror](./MIRROR.md). All development is happening elsewhere.*

Off-grid, resilient mesh communication with strong encryption, forward secrecy and extreme privacy.

![Screenshot](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/1.png)

Nomad Network allows you to build private and resilient communications platforms that are in complete control and ownership of the people that use them. No signups, no agreements, no handover of any data, no permissions and gatekeepers.

Nomad Network is build on [LXMF](https://github.com/markqvist/LXMF) and [Reticulum](https://github.com/markqvist/Reticulum), which together provides the cryptographic mesh functionality and peer-to-peer message routing that Nomad Network relies on. This foundation also makes it possible to use the program over a very wide variety of communication mediums, from packet radio to fiber optics.

Nomad Network does not need any connections to the public internet to work. In fact, it doesn't even need an IP or Ethernet network. You can use it entirely over packet radio, LoRa or even serial lines. But if you wish, you can bridge islanded networks over the Internet or private ethernet networks, or you can build networks running completely over the Internet. The choice is yours. Since Nomad Network uses Reticulum, it is efficient enough to run even over *extremely* low-bandwidth medium, and has been succesfully used over 300bps radio links.

If you'd rather want to use an LXMF client with a graphical user interface, you may want to take a look at [Sideband](https://github.com/markqvist/sideband), which is available for Linux, Android and macOS.

## Notable Features
 - Encrypted messaging over packet-radio, LoRa, WiFi or anything else [Reticulum](https://github.com/markqvist/Reticulum) supports.
 - Zero-configuration, minimal-infrastructure mesh communication
 - Distributed and encrypted message store holds messages for offline users
 - Connectable nodes that can host pages and files
 - Node-side generated pages with PHP, Python, bash or others
 - Built-in text-based browser for interacting with contents on nodes
 - An easy to use and bandwidth efficient markup language for writing pages
 - Page caching in browser

## How do I get started?
The easiest way to install Nomad Network is via pip:

```bash
# Install Nomad Network and dependencies
pip install nomadnet

# Run the client
nomadnet

# Or alternatively run as a daemon, with no user interface
nomadnet --daemon

# List options
nomadnet --help
```

If you are using an operating system that blocks normal user package installation via `pip`, you can return `pip` to normal behaviour by editing the `~/.config/pip/pip.conf` file, and adding the following directive in the `[global]` section:

```text
[global]
break-system-packages = true
```

Alternatively, you can use the `pipx` tool to install Nomad Network in an isolated environment:

```bash
# Install Nomad Network
pipx install nomadnet

# Optionally install Reticulum utilities
pipx install rns

# Optionally install standalone LXMF utilities
pipx install lxmf

# Run the client
nomadnet

# Or alternatively run as a daemon, with no user interface
nomadnet --daemon

# List options
nomadnet --help
```

**Please Note**: If this is the very first time you use pip to install a program on your system, you might need to reboot your system for the program to become available. If you get a "command not found" error or similar when running the program, reboot your system and try again.

The first time the program is running, you will be presented with the **Guide section**, which contains all the information you need to start using Nomad Network.

To use Nomad Network on packet radio or LoRa, you will need to configure your Reticulum installation to use any relevant packet radio TNCs or LoRa devices on your system. See the [Reticulum documentation](https://markqvist.github.io/Reticulum/manual/interfaces.html) for info. For a general introduction on how to set up such a system, take a look at [this post](https://unsigned.io/private-messaging-over-lora/).

If you want to try Nomad Network without building your own physical network, you can connect to the [Unsigned.io RNS Testnet](https://github.com/markqvist/Reticulum#public-testnet) over the Internet, where there is already some Nomad Network and LXMF activity. If you connect to the testnet, you can leave nomadnet running for a while and wait for it to receive announces from other nodes on the network that host pages or services, or you can try connecting directly to some nodes listed here:

 - `abb3ebcd03cb2388a838e70c001291f9` Dublin Hub Testnet Node
 - `ea6a715f814bdc37e56f80c34da6ad51` Frankfurt Hub Testnet Node

To browse pages on a node that is not currently known, open the URL dialog in the `Network` section of the program by pressing `Ctrl+U`, paste or enter the address and select `Go` or press enter. Nomadnet will attempt to discover and connect to the requested node.

### Install on Android
You can install Nomad Network on Android using Termux, but there's a few more commands involved than the above one-liner. The process is documented in the [Android Installation](https://markqvist.github.io/Reticulum/manual/gettingstartedfast.html#reticulum-on-android) section of the Reticulum Manual. Once the Reticulum has been installed according to the linked documentation, Nomad Network can be installed as usual with pip.

For a native Android application with a graphical user interface, have a look at [Sideband](https://github.com/markqvist/Sideband).

### Docker Images

Nomad Network is automatically published as a docker image on Github Packages. Image tags are one of either `master` (for the very latest commit) or the version number (eg `0.2.0`) for a specific release.

```sh
$ docker pull ghcr.io/markqvist/nomadnet:master

# Run nomadnet interactively in a container
$ docker run -it ghcr.io/markqvist/nomadnet:master --textui

# Run nomadnet as a daemon, using config stored on the host machine in specified
# directories, and connect the containers network to the host network (which will
# allow the default AutoInterface to automatically peer with other discovered
# Reticulum instances).
$ docker run -d \
  -v /local/path/nomadnetconfigdir/:/root/.nomadnetwork/ \
  -v /local/path/reticulumconfigdir/:/root/.reticulum/ \
  --network host
  ghcr.io/markqvist/nomadnet:master

# You can also keep the network of the container isolated from the host, but you
# will need to manually configure one or more Reticulum interfaces to reach other
# nodes in a network, by editing the Reticulum configuration file.
$ docker run -d \
  -v /local/path/nomadnetconfigdir/:/root/.nomadnetwork/ \
  -v /local/path/reticulumconfigdir/:/root/.reticulum/ \
  ghcr.io/markqvist/nomadnet:master

# Send daemon log output to console instead of file
$ docker run -i ghcr.io/markqvist/nomadnet:master --daemon --console
```

## Tools & Extensions

Nomad Network is a very flexible and extensible platform, and a variety of community-provided tools, utilities and node-side extensions exist:

- [NomadForum](https://codeberg.org/AutumnSpark1226/nomadForum) ([GitHub mirror](https://github.com/AutumnSpark1226/nomadForum))
- [NomadForecast](https://github.com/faragher/NomadForecast)
- [micron-blog](https://github.com/randogoth/micron-blog)
- [md2mu](https://github.com/randogoth/md2mu)
- [Any2MicronConverter](https://github.com/SebastianObi/Any2MicronConverter)
- [Some nomadnet page examples](https://github.com/SebastianObi/NomadNet-Pages)
- [More nomadnet page examples](https://github.com/epenguins/NomadNet_pages)
- [LXMF-Bot](https://github.com/randogoth/lxmf-bot)
- [LXMF Messageboard](https://github.com/chengtripp/lxmf_messageboard)
- [LXMEvent](https://github.com/faragher/LXMEvent)
- [POPR](https://github.com/faragher/POPR)
- [LXMF Tools](https://github.com/SebastianObi/LXMF-Tools)

## Help & Discussion

For help requests, discussion, sharing ideas or anything else related to Nomad Network, please have a look at the [Nomad Network discussions pages](https://github.com/markqvist/Reticulum/discussions/categories/nomad-network).

## Support Nomad Network
You can help support the continued development of open, free and private communications systems by donating via one of the following channels:

- Monero:
  ```
  84FpY1QbxHcgdseePYNmhTHcrgMX4nFfBYtz2GKYToqHVVhJp8Eaw1Z1EedRnKD19b3B8NiLCGVxzKV17UMmmeEsCrPyA5w
  ```
- Bitcoin
  ```
  bc1pgqgu8h8xvj4jtafslq396v7ju7hkgymyrzyqft4llfslz5vp99psqfk3a6
  ```
- Ethereum
  ```
  0x91C421DdfB8a30a49A71d63447ddb54cEBe3465E
  ```
- Liberapay: https://liberapay.com/Reticulum/

- Ko-Fi: https://ko-fi.com/markqvist


## Development Roadmap

- New major features
    - Network-wide propagated bulletins and discussion threads
    - Collaborative maps and geospatial information sharing
- Minor improvements and fixes
    - Link status (RSSI and SNR) in conversation or conv list
    - Ctrl-M shorcut for jumping to menu
    - Share node with other users / send node info to user
    - Fix internal editor failing on some OSes with no "editor" alias
    - Possibly add a required-width header
    - Improve browser handling of remote link close
    - Better navigation handling when requests fail (also because of closed links)
    - Retry failed messages mechanism
    - Re-arrange buttons to be more consistent
    - Term compatibility notice in readme
    - Selected icon in conversation list
    - Possibly a Search Local Nodes function
    - Possibly add via entry in node info box, next to distance

## Caveat Emptor
Nomad Network is beta software, and should be considered as such. While it has been built with cryptography best-practices very foremost in mind, it _has not_ been externally security audited, and there could very well be privacy-breaking bugs. If you want to help out, or help sponsor an audit, please do get in touch.

## Screenshots

![Screenshot 1](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/1.png)

![Screenshot 2](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/2.png)

![Screenshot 3](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/3.png)

![Screenshot 4](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/4.png)

![Screenshot 5](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/5.png)
