import setuptools

exec(open("nomadnet/_version.py", "r").read())

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="nomadnet",
    version=__version__,
    author="Mark Qvist",
    author_email="mark@unsigned.io",
    description="Communicate Freely",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/markqvist/nomadnet",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points= {
        'console_scripts': ['nomadnet=nomadnet.nomadnet:main']
    },
    install_requires=["rns>=0.4.6", "lxmf>=0.2.8", "urwid>=2.1.2", "qrcode"],
    python_requires=">=3.6",
)
