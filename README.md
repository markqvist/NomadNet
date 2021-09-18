Nomad Network - Communicate Freely
==========

![Screenshot](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/1.png)

The intention with this program is to provide a tool to that allows you to build private and resilient communications platforms that are in complete control and ownership of the people that use them.

Nomad Network is build on [LXMF](https://github.com/markqvist/LXMF) and [Reticulum](https://github.com/markqvist/Reticulum), which together provides the cryptographic mesh functionality and peer-to-peer message routing that Nomad Network relies on. This foundation also makes it possible to use the program over a very wide variety of communication mediums, from packet radio to fiber.

Nomad Network does not need any connections to the public internet to work. In fact, it doesn't even need an IP or Ethernet network. You can use it entirely over packet radio, LoRa or even serial lines. But if you wish, you can bridge islanded Reticulum networks over the Internet or private ethernet networks, or you can build networks running completely over the Internet. The choice is yours.

## Notable Features
 - Encrypted messaging over packet-radio, LoRa, WiFi or anything else [Reticulum](https://github.com/markqvist/Reticulum) supports.
 - Zero-configuration, minimal-infrastructure mesh communication
 - Connectable nodes that can host pages and files
 - Node-side generated pages with PHP, Python, bash or others
 - Built-in text-based browser for interacting with contents on nodes
 - An easy to use and bandwidth efficient markup language for writing pages
 - Page caching in browser

## Current Status
The current version of the program should be considered a beta release. The program works well, but there will most probably be bugs and possibly sub-optimal performance in some scenarios. On the other hand, this is the ideal time to have an influence on the direction of the development of Nomad Network. To do so, join the discussion, report bugs and request features here on the GitHub project.

### Feature roadmap
 - Access control and authentication for nodes, pages and files
 - Network-wide propagated messaging and discussion threads
 - Geospatial information sharing
 - Distributed Marketplace

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

To use Nomad Network on packet radio or LoRa, you will need to configure your Reticulum installation to use any relevant packet radio TNCs or LoRa devices on your system. See the Reticulum documentation for info.

## Caveat Emptor
Nomad Network is beta software, and should be considered as such. While it has been built with cryptography best-practices very foremost in mind, it _has not_ been externally security audited, and there could very well be privacy-breaking bugs. If you want to help out, or help sponsor an audit, please do get in touch.

## Screenshots

![Screenshot 1](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/1.png)

![Screenshot 2](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/2.png)

![Screenshot 3](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/3.png)

![Screenshot 4](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/4.png)

![Screenshot 5](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/5.png)
