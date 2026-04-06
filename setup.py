"""
OrQuanta v4 SDK — PyPI Package Setup
=======================================
Install:
    pip install orquanta

Publish to PyPI:
    pip install build twine
    python -m build
    twine upload dist/*
"""
from setuptools import setup, find_packages
import os

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding="utf-8").read()

setup(
    name="orquanta",
    version="1.0.0",
    author="OrQuanta AI",
    author_email="ops@orquanta.com",
    description="AI-powered autonomous GPU cloud orchestration SDK — run GPU workloads cheaper with zero config",
    long_description=read("SDK_README.md") if os.path.exists("SDK_README.md") else "",
    long_description_content_type="text/markdown",
    url="https://orquanta.com",
    project_urls={
        "Documentation": "https://docs.orquanta.com",
        "Source": "https://github.com/orquanta/orquanta-python",
        "Tracker": "https://github.com/orquanta/orquanta-python/issues",
    },
    packages=find_packages(where=".", include=["orquanta*"]),
    package_dir={"": "."},
    py_modules=["orquanta_sdk"],
    python_requires=">=3.9",
    install_requires=[
        "httpx>=0.25.0",
        "typer>=0.9.0",
        "rich>=13.0.0",
        "pydantic>=2.0.0",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio", "respx"],
    },
    entry_points={
        "console_scripts": [
            "orquanta=orquanta_cli:app",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: System :: Distributed Computing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="gpu cloud ai machine-learning orchestration runpod lambda-labs cost-optimization",
)
