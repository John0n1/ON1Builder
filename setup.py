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
    version="2.1.2",
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
