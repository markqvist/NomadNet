Nomad Network - Communicate Freely
==========

Off-grid, resilient mesh communication with strong encryption, forward secrecy and extreme privacy.

![Screenshot](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/1.png)

Nomad Network Allows you to build private and resilient communications platforms that are in complete control and ownership of the people that use them. No signups, no agreements, no handover of any data, no permissions and gatekeepers.

Nomad Network is build on [LXMF](https://github.com/markqvist/LXMF) and [Reticulum](https://github.com/markqvist/Reticulum), which together provides the cryptographic mesh functionality and peer-to-peer message routing that Nomad Network relies on. This foundation also makes it possible to use the program over a very wide variety of communication mediums, from packet radio to fiber optics.

Nomad Network does not need any connections to the public internet to work. In fact, it doesn't even need an IP or Ethernet network. You can use it entirely over packet radio, LoRa or even serial lines. But if you wish, you can bridge islanded networks over the Internet or private ethernet networks, or you can build networks running completely over the Internet. The choice is yours.

## Notable Features
 - Encrypted messaging over packet-radio, LoRa, WiFi or anything else [Reticulum](https://github.com/markqvist/Reticulum) supports.
 - Zero-configuration, minimal-infrastructure mesh communication
 - Distributed and encrypted message store holds messages for offline users
 - Connectable nodes that can host pages and files
 - Node-side generated pages with PHP, Python, bash or others
 - Built-in text-based browser for interacting with contents on nodes
 - An easy to use and bandwidth efficient markup language for writing pages
 - Page caching in browser

## Current Status
The current version of the program should be considered a beta release. The program works well, but there will most probably be bugs and possibly sub-optimal performance in some scenarios. On the other hand, this is the ideal time to have an influence on the direction of the development of Nomad Network. To do so, join the discussion, report bugs and request features here on the GitHub project.

### Feature roadmap
 - Access control and authentication for nodes, pages and files
 - Network-wide propagated bulletins and discussion threads
 - Geospatial information sharing and collaborative maps

## Dependencies:
 - Python 3
 - RNS
 - LXMF

## How do I get started?
The easiest way to install Nomad Network is via pip:

```bash
# Install Nomad Network and dependencies
pip3 install nomadnet

# Run the client
nomadnet
```

The first time the program is running, you will be presented with the guide section, which contains all the information you need to start using Nomad Network.

To use Nomad Network on packet radio or LoRa, you will need to configure your Reticulum installation to use any relevant packet radio TNCs or LoRa devices on your system. See the [Reticulum documentation](https://markqvist.github.io/Reticulum/manual/interfaces.html) for info.

## Support Nomad Network
You can help support the continued development of open, free and private communications systems by donating via one of the following channels:

- Ethereum: 0x81F7B979fEa6134bA9FD5c701b3501A2e61E897a
- Bitcoin: 3CPmacGm34qYvR6XWLVEJmi2aNe3PZqUuq
- Ko-Fi: https://ko-fi.com/markqvist

## Caveat Emptor
Nomad Network is beta software, and should be considered as such. While it has been built with cryptography best-practices very foremost in mind, it _has not_ been externally security audited, and there could very well be privacy-breaking bugs. If you want to help out, or help sponsor an audit, please do get in touch.

## Screenshots

![Screenshot 1](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/1.png)

![Screenshot 2](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/2.png)

![Screenshot 3](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/3.png)

![Screenshot 4](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/4.png)

![Screenshot 5](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/5.png)
