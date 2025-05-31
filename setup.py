#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import os
from setuptools import find_packages, setup

# read the contents of your README file
here = os.path.abspath(os.path.dirname(__file__))
with io.open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="on1builder",
    version="2.1.0",
    description="Multi-chain blockchain transaction execution framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="ON1Builder Team",
    author_email="john@on1.no",
    url="https://github.com/john0n1/ON1Builder",
    license="MIT",
    python_requires=">=3.12,<3.14",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "aiohttp>=3.12.1",
        "asyncio>=3.4.3",
        "attrs>=25.3.0",
        "eth-account>=0.13.7",
        "eth-hash>=0.5.2",
        "eth-keyfile>=0.7.0",
        "eth-keys>=0.4.0",
        "eth-rlp>=0.3.0",
        "eth-typing>=3.5.0",
        "eth-utils>=5.3.0",
        "eth_abi>=4.2.1",
        "pydantic>=2.11.5",
        "psutil>=7.0.0",
        "python-dotenv>=1.1.0",
        "sqlalchemy>=2.0.41",
        "web3>=7.12.0",
        "typer>=0.16.0",
        "pyyaml>=6.0.0",
    ],
    entry_points={
        "console_scripts": [
            "on1builder=on1builder.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Topic :: System :: Monitoring",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    project_urls={
        "Source": "https://github.com/john0n1/ON1Builder",
        "Tracker": "https://github.com/john0n1/ON1Builder/issues",
    },
)
