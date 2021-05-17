Nomad Network
==========

Communicate Freely.

![Screenshot](https://github.com/markqvist/NomadNet/raw/master/docs/screenshots/3.png)

Nomad Network is built using Reticulum, see [github.com/markqvist/Reticulum](https://github.com/markqvist/Reticulum).

## Notable Features
 - Encrypted messaging over packet-radio, LoRa, WiFi or anything else [Reticulum](https://github.com/markqvist/Reticulum) supports.
 - Zero-configuration, minimal-infrastructure mesh communication

## Current Status

Pre-alpha. At this point Nomad Network is usable as a basic messaging client over Reticulum networks, but only the very core features have been implemented. Development is ongoing and current features being implemented are:

 - Propagated messaging and discussion threads
 - Connectable nodes that can host pages, files and other resources
 - Collaborative information sharing and spatial map-style "wikis"

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

To use Nomad Network on packet radio or LoRa, you will need to configure your Reticulum installation to use any relevant packet radio TNCs or LoRa devices on your system. See the Reticulum documentation for info.

## Caveat Emptor
Nomad Network is experimental software, and should be considered as such. While it has been built with cryptography best-practices very foremost in mind, it _has not_ been externally security audited, and there could very well be privacy-breaking bugs. If you want to help out, or help sponsor an audit, please do get in touch.