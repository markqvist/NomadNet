>> Nomad Network - Communicate Freely

Off-grid, resilient mesh communication with strong encryption, forward secrecy and extreme privacy.

Nomad Network allows you to build private and resilient communications platforms that are in complete control and ownership of the people that use them. No signups, no agreements, no handover of any data, no permissions and gatekeepers.

Nomad Network is build on `_`!`[LXMF`a8d24177d946de4f1f0a0fe1af9a1338:/page/repo.mu`g=reticulum|r=lxmf]`!`_ and `_`!`[Reticulum`a8d24177d946de4f1f0a0fe1af9a1338:/page/repo.mu`g=reticulum|r=reticulum]`!`_, which together provides the cryptographic mesh functionality and peer-to-peer message routing that Nomad Network relies on. This foundation also makes it possible to use the program over a very wide variety of communication mediums, from packet radio to fiber optics.

Nomad Network does not need any connections to the public internet to work. In fact, it doesn't even need an IP or Ethernet network. You can use it entirely over packet radio, LoRa or even serial lines. But if you wish, you can bridge islanded networks over the Internet or private ethernet networks, or you can build networks running completely over the Internet. The choice is yours. Since Nomad Network uses Reticulum, it is efficient enough to run even over `*extremely`* low-bandwidth medium, and has been succesfully used over 300bps radio links.

If you'd rather want to use an LXMF client with a graphical user interface, you may want to take a look at `_`!`[Sideband`a8d24177d946de4f1f0a0fe1af9a1338:/page/repo.mu`g=reticulum|r=sideband]`!`_, which is available for Linux, Android, Windows and macOS.

>> Notable Features

 • Encrypted messaging over packet-radio, LoRa, WiFi or anything else `_`!`[Reticulum`a8d24177d946de4f1f0a0fe1af9a1338:/page/repo.mu`g=reticulum|r=reticulum]`!`_ supports.
 • Zero-configuration, minimal-infrastructure mesh communication
 • Distributed and encrypted message store holds messages for offline users
 • Connectable nodes that can host pages and files
 • Image rendering support in terminals that support it
 • Node-side generated pages with PHP, Python, bash or others
 • Built-in text-based browser for interacting with contents on nodes
 • Built-in RRC client for live, many-to-many chat
 • An easy to use and bandwidth efficient markup language for writing pages
 • Page caching in browser

>> How do I get started?

The easiest way to install Nomad Network is via `B333pip`b:

`B333
`=
# Install Nomad Network and dependencies
pip install nomadnet

# Run the client
nomadnet

# Or alternatively run as a daemon, with no user interface
nomadnet --daemon

# List options
nomadnet --help
`=
`b

If you are using an operating system that blocks normal user package installation via `B333pip`b, you can return `B333pip`b to normal behaviour by editing the `B333~/.config/pip/pip.conf`b file, and adding the following directive in the `B333[global]`b section:

`B333
`=
[global]
break-system-packages = true
`=
`b

Alternatively, you can use the `B333pipx`b tool to install Nomad Network in an isolated environment:

`B333
`=
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
`=
`b

`!Please Note`!: If this is the very first time you use pip to install a program on your system, you might need to reboot your system for the program to become available. If you get a "command not found" error or similar when running the program, reboot your system and try again.

The first time the program is running, you will be presented with the `!Guide section`!, which contains all the information you need to start using Nomad Network.

To use Nomad Network on packet radio or LoRa, you will need to configure your Reticulum installation to use any relevant packet radio TNCs or LoRa devices on your system. See the `_`!`[Reticulum documentation`a8d24177d946de4f1f0a0fe1af9a1338:/page/blob.mu`g=reticulum|r=reticulum|ref=HEAD|path=docs/markdown/index.md]`!`_ for info.

If you want to try Nomad Network without building your own physical network, you can connect to the `_`!`[distributed RNS backbone`a8d24177d946de4f1f0a0fe1af9a1338:/page/blob.mu`g=reticulum|r=reticulum|ref=HEAD|path=docs/markdown/gettingstartedfast.md|anchor=connect-to-the-distributed-backbone]`!`_ over the Internet, where there is already quite a bit of Nomad Network and LXMF activity. If you connect to the testnet, you can leave nomadnet running for a while and wait for it to receive announces from other nodes on the network that host pages or services, or you can try connecting directly to some nodes listed here:

 • `!`_`[9ce92808be498e9e05590ff27cbfdfe4]`_`! The rns.recipes forum
 • `!`_`[a4a5e861626ce97c9aa544d9ecdf6d22]`_`! rmap.world

To browse pages on a node that is not currently known, open the URL dialog in the `!Network`! section of the program by pressing `!Ctrl+U`!, paste or enter the address and select `!Go`! or press enter. Nomadnet will attempt to discover and connect to the requested node.

>>> Install on Android

You can install Nomad Network on Android using Termux, but there's a few more commands involved than the above one-liner. The process is documented in the `_`!`[Android Installation`a8d24177d946de4f1f0a0fe1af9a1338:/page/blob.mu`g=reticulum|r=reticulum|ref=HEAD|path=docs/markdown/gettingstartedfast.md|anchor=reticulum-on-android]`!`_ section of the Reticulum Manual. Once the Reticulum has been installed according to the linked documentation, Nomad Network can be installed as usual with pip.

For a native Android application with a graphical user interface, have a look at `_`!`[Sideband`a8d24177d946de4f1f0a0fe1af9a1338:/page/repo.mu`g=reticulum|r=sideband]`!`_.

>> Help & Discussion

For help requests, discussion, sharing ideas or anything else related to Nomad Network, please have a look at the `_`!`[rns.recipes forum`9ce92808be498e9e05590ff27cbfdfe4]`!`_.

>> Support Nomad Network

For this to be possible, I need your help. Please support the continued development of open, free and private communications systems by donating via one of the following channels:

• `!Monero`!
  84FpY1QbxHcgdseePYNmhTHcrgMX4nFfBYtz2GKYToqHVVhJp8Eaw1Z1EedRnKD19b3B8NiLCGVxzKV17UMmmeEsCrPyA5w

• `!Bitcoin`!
  bc1pgqgu8h8xvj4jtafslq396v7ju7hkgymyrzyqft4llfslz5vp99psqfk3a6

• `!Ethereum`!
  0x91C421DdfB8a30a49A71d63447ddb54cEBe3465E

• `!Liberapay`!
  `[https://liberapay.com/Reticulum/]

• `!Ko-Fi`!
  `[https://ko-fi.com/markqvist]

>> Caveat Emptor

Nomad Network is experimental software, and should be considered as such. Use at your own risk and responsibility.
